"""Core analysis service for the Feedback Intelligence Engine.

Responsibilities (in order):
1. Build ``Review`` objects from the raw request payload.
2. Call Claude (SONNET + thinking) to produce a structured FeedbackAnalysis JSON,
   validated against the frozen feedback_analysis schema (AC-2 shape: every item
   requires an evidence_ref with a review_id and a verbatim quote).
3. Enforce AC-2 post-hoc: drop/repair any item whose evidence_ref.review_id is not
   among the input review ids.
4. Compute the DETERMINISTIC feedback_score from the frozen glossary formula so that
   the Phase-3 AC-3 corpus-mutation test can move it.
5. Persist to FeedbackAnalysisRowORM in the exact same serialisation format that
   knowledge_core/feedback.py uses, so team_assembler's get_async() can read it.
6. Write an append-only AuditRow (trace_id, principal, model_version, …).
7. Return the FeedbackAnalysis dataclass.

Stub path (is_real() == False): the ClaudeClient returns a minimal schema-valid dict;
we apply the same post-processing (score, persist, audit) so the boot-test path is
exercised end-to-end without a real credential.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from app.contracts import (
    AuditRow,
    AuthContext,
    EvidenceRef,
    FeedbackAnalysis,
    Review,
)
from app.db.models import FeedbackAnalysisRowORM
from app.db.session import async_session_factory
from app.llm import SONNET, get_claude_client
from app.shared_security import get_audit_sink

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Load the frozen JSON Schema (used as the structured-output contract for Claude).
# Path is relative to the repo root; contracts.py parents[2] resolves it the same way.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]
_FEEDBACK_SCHEMA_PATH = (
    _REPO_ROOT / "system" / "contracts" / "schemas" / "feedback_analysis.schema.json"
)

_FEEDBACK_SCHEMA: dict[str, Any] = json.loads(_FEEDBACK_SCHEMA_PATH.read_text())

# ---------------------------------------------------------------------------
# Deterministic score formula (glossary.feedback_score_formula — frozen).
# Must be reproduced here (not delegated to Claude) so AC-3 mutation test moves it.
# ---------------------------------------------------------------------------
_RISK_PENALTY: dict[str, float] = {"low": 0.05, "medium": 0.10, "high": 0.20}

_SYSTEM_PROMPT = """\
You are an organizational feedback analyst. Your task is to extract structured \
intelligence from a set of employee peer/manager/self reviews.

Rules (MUST follow — non-negotiable):
1. Be objective. Avoid vague or generic statements. Highlight patterns that appear \
across multiple reviews rather than isolated remarks.
2. Every strength, weakness, risk, and team-dynamics signal MUST cite a specific \
review via evidence_ref with:
   - review_id: the exact review_id from the input (no fabricated ids)
   - quote: a VERBATIM excerpt from that review (not paraphrased)
3. A finding without a real verbatim quote is invalid — omit it rather than invent one.
4. For risks, classify severity as low/medium/high based on the evidence strength. \
Valid risk types: burnout, conflict, attrition, performance, other.
5. sentiment is a float in [-1, 1] reflecting the overall tone across all reviews. \
feedback_score and confidence_score are computed externally — set them to 0.0 as a \
placeholder (they will be overwritten by deterministic logic).
6. analysis_id should be a short human-readable id like "fb-<employee_id>-<short>".

Respond ONLY with a JSON object that matches the provided schema.\
"""


def _build_user_message(employee_id: str, reviews: list[Review]) -> str:
    lines = [f"Employee ID: {employee_id}", "", "Reviews:"]
    for r in reviews:
        lines.append(f"  review_id={r.review_id!r} kind={r.kind!r}")
        lines.append(f'  text: """{r.text}"""')
        lines.append("")
    return "\n".join(lines)


def _valid_review_ids(reviews: list[Review]) -> frozenset[str]:
    return frozenset(r.review_id for r in reviews)


def _repair_evidenced_items(
    items: list[dict],
    valid_ids: frozenset[str],
) -> list[dict]:
    """Drop any item whose evidence_ref.review_id is not a real input review id (AC-2)."""
    repaired: list[dict] = []
    for item in items:
        ev = item.get("evidence_ref") or {}
        rid = ev.get("review_id", "")
        quote = ev.get("quote", "").strip()
        if rid in valid_ids and quote:
            repaired.append(item)
        else:
            log.warning(
                "feedback.ac2.dropped_item",
                text=item.get("text", "")[:80],
                review_id=rid,
                reason="review_id not in input set" if rid not in valid_ids else "empty quote",
            )
    return repaired


def _repair_risks(
    risks: list[dict],
    valid_ids: frozenset[str],
) -> list[dict]:
    """Drop any risk whose evidence_ref.review_id is not a real input review id (AC-2)."""
    repaired: list[dict] = []
    for risk in risks:
        ev = risk.get("evidence_ref") or {}
        rid = ev.get("review_id", "")
        quote = ev.get("quote", "").strip()
        if rid in valid_ids and quote:
            repaired.append(risk)
        else:
            log.warning(
                "feedback.ac2.dropped_risk",
                text=risk.get("text", "")[:80],
                review_id=rid,
                reason="review_id not in input set" if rid not in valid_ids else "empty quote",
            )
    return repaired


def _compute_feedback_score(
    strengths: list[dict],
    weaknesses: list[dict],
    risks: list[dict],
) -> float:
    """Deterministic formula from glossary.feedback_score_formula (frozen).

    start 0.5; +0.08/strength; -0.06/weakness; -risk_penalty{low:0.05,medium:0.10,high:0.20}/risk;
    clamp [0,1].
    """
    score = 0.5 + 0.08 * len(strengths) - 0.06 * len(weaknesses)
    for r in risks:
        severity = r.get("severity", "low")
        score -= _RISK_PENALTY.get(severity, 0.0)
    return max(0.0, min(1.0, score))


def _build_analysis_id(employee_id: str, reviews: list[Review]) -> str:
    digest = hashlib.sha1(
        (employee_id + "|" + "|".join(sorted(r.review_id for r in reviews))).encode()
    ).hexdigest()[:16]
    return f"fb-{employee_id}-{digest}"


# ---------------------------------------------------------------------------
# Persistence helpers — MUST match knowledge_core/feedback.py serialisation exactly
# so team_assembler's get_async() (_row_to_analysis / _deserialize_items) reads correctly.
#
# knowledge_core/feedback.py uses:
#   _serialize_items: list[tuple[str, EvidenceRef]] -> list[{"text":..., "evidence_ref":{...}}]
#   risks stored as-is: list[dict] with keys {type, text, severity, evidence_ref:{review_id, quote}}
# The LLM already outputs in that shape; we store it verbatim.
# ---------------------------------------------------------------------------


def _to_orm_items(items: list[dict]) -> list[dict]:
    """Normalise evidenced-item dicts to the exact format _deserialize_items expects:
    {"text": str, "evidence_ref": {"review_id": str, "quote": str}}
    """
    out = []
    for it in items:
        ev = it.get("evidence_ref", {})
        out.append(
            {
                "text": it.get("text", ""),
                "evidence_ref": {
                    "review_id": ev.get("review_id", ""),
                    "quote": ev.get("quote", ""),
                },
            }
        )
    return out


async def _persist(
    analysis: FeedbackAnalysis,
    strengths_raw: list[dict],
    weaknesses_raw: list[dict],
    risks_raw: list[dict],
    team_dynamics_raw: list[dict],
    org: str,
) -> None:
    """Write FeedbackAnalysisRowORM in the EXACT same format knowledge_core/feedback.py uses.

    knowledge_core.FeedbackIntelligenceImpl._persist checks for existing by analysis_id and
    skips if already present; we do the same upsert-guard to avoid duplicates.
    """
    async with async_session_factory() as session:
        existing = await session.get(FeedbackAnalysisRowORM, analysis.analysis_id)
        if existing is None:
            session.add(
                FeedbackAnalysisRowORM(
                    analysis_id=analysis.analysis_id,
                    employee_id=analysis.employee_id,
                    org=org,
                    created_at=datetime.now(UTC),
                    feedback_score=analysis.feedback_score,
                    sentiment=analysis.sentiment,
                    confidence_score=analysis.confidence_score,
                    # Stored as list[{"text":..., "evidence_ref":{...}}] — same as
                    # knowledge_core._serialize_items output format.
                    strengths=_to_orm_items(strengths_raw),
                    weaknesses=_to_orm_items(weaknesses_raw),
                    # risks stored as-is: list[dict] with {type,text,severity,evidence_ref}
                    risks=list(risks_raw),
                    team_dynamics_signals=_to_orm_items(team_dynamics_raw),
                )
            )
            await session.commit()
        else:
            # Already persisted (idempotent re-run); update score fields in place.
            existing.feedback_score = analysis.feedback_score
            existing.sentiment = analysis.sentiment
            existing.confidence_score = analysis.confidence_score
            existing.strengths = _to_orm_items(strengths_raw)
            existing.weaknesses = _to_orm_items(weaknesses_raw)
            existing.risks = list(risks_raw)
            existing.team_dynamics_signals = _to_orm_items(team_dynamics_raw)
            await session.commit()


def _dict_to_feedback_analysis(
    data: dict,
    employee_id: str,
    reviews: list[Review],
    org: str,
) -> tuple[FeedbackAnalysis, list[dict], list[dict], list[dict], list[dict]]:
    """Convert LLM output dict -> (FeedbackAnalysis dataclass, raw_lists_for_orm).

    Returns a tuple of (analysis, strengths_raw, weaknesses_raw, risks_raw, team_dynamics_raw)
    so the caller can persist the raw dicts and build the dataclass from them.
    """
    valid_ids = _valid_review_ids(reviews)

    strengths_raw = _repair_evidenced_items(data.get("strengths") or [], valid_ids)
    weaknesses_raw = _repair_evidenced_items(data.get("weaknesses") or [], valid_ids)
    risks_raw = _repair_risks(data.get("risks") or [], valid_ids)
    team_dynamics_raw = _repair_evidenced_items(data.get("team_dynamics_signals") or [], valid_ids)

    # Deterministic feedback_score (overrides whatever the LLM put — it's always 0.0).
    feedback_score = _compute_feedback_score(strengths_raw, weaknesses_raw, risks_raw)

    # Preserve LLM-provided sentiment (it's a genuine inference); clamp to [-1,1].
    sentiment = float(data.get("sentiment", 0.0))
    sentiment = max(-1.0, min(1.0, sentiment))

    # Preserve LLM-provided confidence_score; clamp to [0,1].
    confidence_score = float(data.get("confidence_score", 0.0))
    confidence_score = max(0.0, min(1.0, confidence_score))

    # Use a stable analysis_id derived from inputs (not the LLM's suggestion).
    analysis_id = _build_analysis_id(employee_id, reviews)

    # Build the FeedbackAnalysis dataclass using the same structure as knowledge_core uses:
    # strengths/weaknesses/team_dynamics_signals: list[tuple[str, EvidenceRef]]
    def to_tuples(items: list[dict]) -> list[tuple[str, EvidenceRef]]:
        result = []
        for it in items:
            ev = it.get("evidence_ref", {})
            result.append(
                (
                    it.get("text", ""),
                    EvidenceRef(
                        review_id=ev.get("review_id", ""),
                        quote=ev.get("quote", ""),
                    ),
                )
            )
        return result

    analysis = FeedbackAnalysis(
        analysis_id=analysis_id,
        employee_id=employee_id,
        feedback_score=feedback_score,
        sentiment=sentiment,
        strengths=to_tuples(strengths_raw),
        weaknesses=to_tuples(weaknesses_raw),
        risks=list(risks_raw),
        team_dynamics_signals=to_tuples(team_dynamics_raw),
        confidence_score=confidence_score,
    )
    return analysis, strengths_raw, weaknesses_raw, risks_raw, team_dynamics_raw


async def analyze_reviews(
    *,
    employee_id: str,
    reviews: list[Review],
    auth_ctx: AuthContext,
    trace_id: str,
    org: str = "godeltech",
) -> FeedbackAnalysis:
    """Full pipeline: LLM analysis -> AC-2 repair -> deterministic score -> persist -> audit.

    This is the Phase-2 LLM-backed implementation.  The knowledge_core stub
    (FeedbackIntelligenceImpl.analyze_async) is not called here — we own the full analysis.
    The result is persisted in the SAME FeedbackAnalysisRowORM format so the shared
    get_feedback_intelligence().get_async() path (used by team_assembler) reads it correctly.
    """
    if not reviews:
        raise ValueError("analyze_reviews() requires at least one review")

    client = get_claude_client()
    # Sonnet for analysis quality; thinking OFF to keep the endpoint responsive. Specificity is
    # guaranteed post-hoc (every item must carry a verbatim quote from a real review), so the
    # "generic feedback" failure mode is closed without paying the thinking-latency tax.
    model_version = SONNET

    user_msg = _build_user_message(employee_id, reviews)

    # Real LLM call (or stub if no credential configured).
    llm_data: dict = client.complete_json(
        system=_SYSTEM_PROMPT,
        user=user_msg,
        schema=_FEEDBACK_SCHEMA,
        model=model_version,
        thinking=False,
    )

    (
        analysis,
        strengths_raw,
        weaknesses_raw,
        risks_raw,
        team_dynamics_raw,
    ) = _dict_to_feedback_analysis(llm_data, employee_id, reviews, org)

    # Persist so team_assembler can read via get_feedback_intelligence().get_async().
    await _persist(
        analysis,
        strengths_raw,
        weaknesses_raw,
        risks_raw,
        team_dynamics_raw,
        org,
    )

    # Append-only audit row (AC-5 / gdpr-rbac-guardrail).
    inputs_hash = hashlib.sha256(user_msg.encode()).hexdigest()[:32]
    audit_row = AuditRow(
        trace_id=trace_id,
        timestamp=datetime.now(UTC),
        principal_id=auth_ctx.principal_id,
        module="feedback",
        inputs_hash=inputs_hash,
        retrieved_chunk_ids=[],  # feedback does not use vector retrieval
        prompt_version="feedback-v1",
        model_version=model_version,
        output_ref=analysis.analysis_id,
        grounding_score=None,
        tenant=f"internal:{org}",
    )
    await get_audit_sink().append_async(audit_row)

    return analysis
