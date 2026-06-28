"""Public RAG chatbot pipeline (REQ-003/004/005/006, AC-1/AC-5).

One entrypoint, :func:`answer_query`, runs the grounded pipeline:

    detect_intent -> semantic_search (PUBLIC_AUTH_CONTEXT, run_in_threadpool)
      -> build citation-tagged context -> Claude complete_json(rag_answer schema)
      -> grounding/abstain + citation-resolution -> audit -> RAGAnswer

Grounding discipline (the anti-hallucination core):
- Retrieval is via the SHARED brain accessor ``get_knowledge_core()`` on the frozen
  ``PUBLIC_AUTH_CONTEXT`` — retrieval is already tenant+domain scoped, so the public surface
  physically cannot return employee_profiles/feedback (REQ-013).
- Claude is told to answer ONLY from the tagged context and emit per-claim source_id citations.
- After the call we ENFORCE grounding regardless of what the model claims:
  * every citation.source_id must be one of the retrieved chunk ids (others are dropped);
  * a substantive answer with zero resolving citations -> abstain (ask for clarification);
  * empty retrieval -> abstain;
  * ClaudeRefusal -> abstain.
  (The faithfulness-judge score is the Phase-3 runtime gate, not enforced here.)
- Every call writes an append-only AuditRow keyed by trace_id (module="chatbot", tenant="public").

Latency: retrieval k is small (5), Claude runs on Sonnet with thinking disabled to keep the
<2s SLA. The sync ``semantic_search`` is dispatched via ``run_in_threadpool`` so it never blocks
the event loop.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from app.chatbot.intent import detect_intent, domain_filter_for
from app.chatbot.prompts import GROUNDING_PROMPT_VERSION, GROUNDING_SYSTEM_PROMPT
from app.contracts import (
    PUBLIC_AUTH_CONTEXT,
    AuditRow,
    RetrievedChunk,
)

# Accessors come from the REAL impl packages — the ones re-exported by app.contracts are the
# frozen stubs that raise NotImplementedError (see app.contracts docstring). AC-4: every module
# routes through these single shared accessors, never a private duplicate.
from app.knowledge_core import get_knowledge_core
from app.llm import SONNET, ClaudeRefusal, ClaudeUnavailable, get_claude_client
from app.observability import span
from app.shared_security import get_audit_sink

# Repo root: .../backend/app/chatbot/service.py -> parents[3] is the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_RAG_SCHEMA_PATH = _REPO_ROOT / "system" / "contracts" / "schemas" / "rag_answer.schema.json"

_RETRIEVE_K = 5
_ABSTAIN_ANSWER = (
    "I don't have enough information to answer that confidently. Could you rephrase or share a "
    "bit more about what you're looking for?"
)


@dataclass(frozen=True)
class ChatResult:
    """The validated RAGAnswer payload plus the trace_id for the X-Trace-Id response header."""

    answer: dict  # schema-valid RAGAnswer dict (answer/citations/intent/confidence/abstained)
    trace_id: str


@lru_cache
def _rag_schema() -> dict:
    """Load and cache the frozen rag_answer JSON Schema (read-only contract)."""
    return json.loads(_RAG_SCHEMA_PATH.read_text(encoding="utf-8"))


def _build_context(chunks: list[RetrievedChunk]) -> str:
    """Citation-tagged context: each chunk labeled with its source_id so the model can cite it."""
    blocks = []
    for c in chunks:
        blocks.append(f"[source_id: {c.source_id}] (domain={c.domain})\n{c.text}")
    return "\n\n".join(blocks)


def _abstain_answer(intent: str, note: str) -> dict:
    """A schema-valid abstaining RAGAnswer (clarification-seeking, no/empty citations)."""
    return {
        "answer": note,
        "citations": [],
        "intent": intent,
        "confidence": 0.0,
        "abstained": True,
    }


def _resolve_citations(answer: dict, valid_ids: set[str]) -> dict:
    """Drop any citation whose source_id was NOT actually retrieved (citation-resolution, AC-1).

    Then enforce abstain: if the answer is substantive (non-empty, not already abstaining) but no
    citation resolves to a retrieved chunk, flip to an abstaining clarification ask.
    """
    raw_citations = answer.get("citations") or []
    resolved = [c for c in raw_citations if c.get("source_id") in valid_ids]
    answer["citations"] = resolved

    if answer.get("abstained"):
        # Model already chose to abstain; keep it (citations already pruned to resolving ones).
        return answer

    substantive = bool((answer.get("answer") or "").strip())
    if substantive and not resolved:
        # Substantive but ungrounded -> never ship it; abstain instead.
        answer["answer"] = _ABSTAIN_ANSWER
        answer["citations"] = []
        answer["confidence"] = 0.0
        answer["abstained"] = True
    return answer


def _audit(
    *,
    trace_id: str,
    chunks: list[RetrievedChunk],
    query: str,
    answer: dict,
    model_version: str,
) -> None:
    """Best-effort append-only AuditRow for this RAG decision (keyed by trace_id, tenant=public)."""
    row = AuditRow(
        trace_id=trace_id,
        timestamp=datetime.now(UTC),
        principal_id=PUBLIC_AUTH_CONTEXT.principal_id,
        module="chatbot",
        inputs_hash=hashlib.sha256(query.encode("utf-8")).hexdigest(),
        retrieved_chunk_ids=[c.source_id for c in chunks],
        prompt_version=GROUNDING_PROMPT_VERSION,
        model_version=model_version,
        output_ref=trace_id,
        grounding_score=float(answer.get("confidence", 0.0) or 0.0),
        tenant="public",
    )
    # The sync Protocol method schedules the async DB write (fire-and-forget inside a running
    # loop) and is safe to call from anywhere. Audit is best-effort — a DB outage or missing DB
    # at boot must never break the answer path.
    try:
        get_audit_sink().append(row)
    except Exception:  # noqa: BLE001 - audit must not 500 the user
        pass


async def answer_query(query: str, trace_id: str) -> ChatResult:
    """Run the grounded RAG pipeline for one public query and return a schema-valid RAGAnswer.

    Always returns a valid RAGAnswer (grounded or abstaining), including in stub mode — but real
    grounding only holds with a real Claude credential (Phase-3 gate).
    """
    client = get_claude_client()
    model_version = SONNET  # grounded RAG answers; thinking disabled below to fit the <2s SLA

    # 1. Intent -> public domain filter (REQ-006).
    with span("chatbot.intent"):
        intent = detect_intent(query)
        dfilter = domain_filter_for(intent)

    # 2. Retrieve from the shared brain on the PUBLIC (PII-free) context, off the event loop.
    with span("chatbot.retrieve", intent=intent, k=_RETRIEVE_K):
        core = get_knowledge_core()
        chunks: list[RetrievedChunk] = await run_in_threadpool(
            core.semantic_search, query, dfilter, PUBLIC_AUTH_CONTEXT, _RETRIEVE_K
        )

    # 3. Empty retrieval is a NORMAL abstain path (REQ-005).
    if not chunks:
        answer = _abstain_answer(intent, _ABSTAIN_ANSWER)
        _audit(
            trace_id=trace_id,
            chunks=chunks,
            query=query,
            answer=answer,
            model_version=model_version,
        )
        return ChatResult(answer=answer, trace_id=trace_id)

    valid_ids = {c.source_id for c in chunks}

    # 4. Build citation-tagged context and call Claude (schema-validated, no thinking for <2s).
    with span("chatbot.build_context", chunks=len(chunks)):
        context = _build_context(chunks)
        user_msg = (
            f"QUERY:\n{query}\n\n"
            f"CONTEXT (cite passages by their [source_id]):\n{context}\n\n"
            "Answer using ONLY the CONTEXT above. If it is insufficient, abstain."
        )

    with span("chatbot.claude_call", model=model_version):
        try:
            answer = await run_in_threadpool(
                _complete,
                client,
                GROUNDING_SYSTEM_PROMPT,
                user_msg,
                _rag_schema(),
                model_version,
            )
        except (ClaudeRefusal, ClaudeUnavailable):
            # Refusal OR API unavailable (rate-limit/etc) -> abstain, never crash (REQ-005).
            answer = _abstain_answer(intent, _ABSTAIN_ANSWER)
            _audit(
                trace_id=trace_id,
                chunks=chunks,
                query=query,
                answer=answer,
                model_version=model_version,
            )
            return ChatResult(answer=answer, trace_id=trace_id)

    # The model controls `intent` per the schema, but our detector is authoritative for routing;
    # keep them consistent so the audited/returned intent matches the domains actually searched.
    answer["intent"] = intent

    # 5. Grounding / abstain + citation-resolution (AC-1 enforcement).
    with span("chatbot.grounding_check"):
        answer = _resolve_citations(answer, valid_ids)

    # 6. Audit (append-only, keyed by trace_id, tenant=public).
    _audit(
        trace_id=trace_id, chunks=chunks, query=query, answer=answer, model_version=model_version
    )
    return ChatResult(answer=answer, trace_id=trace_id)


def _complete(client, system: str, user: str, schema: dict, model: str) -> dict:
    """Thin sync helper so the (sync) Claude client runs in the threadpool, not the event loop."""
    return client.complete_json(
        system=system,
        user=user,
        schema=schema,
        model=model,
        thinking=False,
    )
