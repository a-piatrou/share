---
name: ghostwire-schemas
description: GHOSTWIRE output contracts and acceptance criteria. Use whenever generating, validating, or reasoning about the RAG chatbot answer, Feedback Intelligence analysis, or AI Team Assembler output, or when wiring the four automatic-fail acceptance checks (anti-hallucination, anti-generic feedback, behavioral-data use, shared-intelligence use) and the explainability requirement.
---

# GHOSTWIRE output contracts & acceptance criteria

The three LLM output shapes are committed JSON Schemas under `system/contracts/schemas/`.
They are **structured-output-safe** (no numeric/length constraints; `additionalProperties:false`)
so they double as `output_config.format` schemas AND `jsonschema`/Pydantic validators.

| Output | Schema file | Key contract field |
|---|---|---|
| RAG answer | `rag_answer.schema.json` | `citations[]` (each `{source_id, snippet}`) + `abstained` |
| Feedback analysis | `feedback_analysis.schema.json` | every item has `evidence_ref {review_id, quote}` |
| Team assembly | `team_assembly.schema.json` | every member has `feedback_signal_ref {source, signal}` + `rationale` |

Validate **every** Claude response against its schema before use; malformed/ungrounded output
must fail fast (Pydantic `model_validate` / `jsonschema.validate`).

## Acceptance criteria (derived from the GHOSTWIRE failure conditions)

Each is `automatic-fail`. **Schema-presence is necessary but NOT sufficient** — the *semantic*
verdicts (AC-1/3/4) are proven at the Phase-3 runtime gate, not by build-time field checks.

- **AC-1 — no hallucination** (`runtime`). A substantive `answer` MUST carry ≥1 citation, and
  each `source_id` MUST **resolve to a chunk actually returned** by `KnowledgeCore.semantic_search`
  for that query. If grounding is insufficient → `abstained=true` and the answer asks for
  clarification. *Build-time:* schema requires `citations[]`. *Runtime gate:* citation-resolution
  + a faithfulness/groundedness judge (Ragas/DeepEval-style); below threshold ⇒ abstain, never guess.
- **AC-2 — not generic** (`judge`). Every feedback item has an `evidence_ref` pointing at a real
  input review with a verbatim `quote`. Enforce as a human/LLM-judge signal, **not a denylist**
  (denylists are trivially paraphrased around).
- **AC-3 — behavioral data is used** (`runtime`). Every team member has a `feedback_signal_ref`
  whose `source` is a real `FeedbackIntelligence` record. *Runtime gate:* mutate a candidate's
  feedback in the corpus and assert their `match_score`/selection **changes** — proves the score
  actually consumes behavioral data rather than ignoring it.
- **AC-4 — shared intelligence is used** (`runtime`). Build-time static check: every module
  imports the SAME `KnowledgeCore` + `EmbeddingService` (no private duplicate retrieval/embedding).
  *Runtime gate (the real proof):* mutate the corpus and assert chatbot answers **change** — proves
  modules route through the one brain at runtime, not merely import it.
- **AC-5 — explainability** (`static`+`judge`, cross-module). Every decision is explainable:
  RAG `citations`, feedback `evidence_ref`, team `rationale`/`feedback_signal_ref`. A module that
  emits a decision with no explanation field is invalid ("can't explain itself = can't be trusted").

## Grounding discipline (chatbot)

Context-only prompting: retrieve from the vector DB, build a **citation-tagged** context, instruct
Claude to answer **only** from provided context and emit per-claim `source_id`s. Run the faithfulness
check and **abstain** below threshold rather than answer. Target response time **< 2s** (keep
retrieval k small, stream the answer, cache the system prompt). See `stack-conventions` for the
Claude client + caching, and `gdpr-rbac-guardrail` for tenant scoping of retrieval.
