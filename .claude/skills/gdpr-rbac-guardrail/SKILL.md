---
name: gdpr-rbac-guardrail
description: GHOSTWIRE's hard non-functional requirements — GDPR, role-based access control, append-only audit logs of AI decisions, and no external exposure of sensitive employee data. Use whenever touching auth, retrieval, data models, the Claude calls, logging, or the public chatbot. These are cross-cutting and OWNED by a single shared library, not any one feature module.
---

# GDPR / RBAC / audit guardrail

These NFRs span every module, so one-worktree-per-module assigns them **no owner** and
isolation prevents convergence. **Mitigation: a single shared `shared_security` library**
(its own module/worktree, frozen in Phase 0) that every module consumes. A green build that
ships PII to the public chatbot tenant is **worse than no automation** — it manufactures false
confidence on the highest-severity requirement. Tested adversarially in the Phase-3 runtime gate.

## RBAC — defense in depth (two layers, both required)
1. **API layer** — a FastAPI dependency resolves the principal → `AuthContext` (user id, role,
   org/tenant, allowed domains) on every request; endpoints declare required role.
2. **Retrieval layer** — `AuthContext` is propagated into **every** `KnowledgeCore.semantic_search`
   call and maps the principal to a **Weaviate tenant**, so retrieval itself **cannot** return
   unauthorized employee data. Never filter only in application code after retrieval.
- **Public chatbot runs on a PII-free tenant.** Company/job/case-study data only; employee
  profiles, feedback, and reviews are NEVER in the public tenant.

## GDPR / data protection
- Sensitive employee data (CVs, feedback, profiles) stays **in-VPC** (self-hosted Weaviate +
  private-IP Cloud SQL); no external/managed store for it. Minimize PII in prompts sent to
  Claude; never put secrets/PII in logs or memory files.
- Support data-subject operations by design: deletable/rectifiable records, retention limits,
  and the ability to purge an employee's data across Postgres + Weaviate.

## Audit — append-only AI-decision trail
Every AI decision (RAG answer, feedback analysis, team selection) writes an **append-only**
`AuditRow` keyed by `trace_id`:
`{ trace_id, timestamp, principal, module, inputs_hash, retrieved_chunk_ids, prompt_version,
model_version, output_ref, grounding_score }`. Stored in Cloud SQL; correlated with the OTel
`trace_id` (see `stack-conventions`). Append-only: no updates/deletes on audit rows.

## Explainability (ties to AC-5)
Every decision must answer "why this answer / why this person/team": RAG `citations`, feedback
`evidence_ref`, team `rationale` + `feedback_signal_ref`. A decision emitted with no
explanation is invalid.

## Build-time vs runtime
Build-time can check **structure** (dependency on `shared_security`, presence of `auth_ctx` in
the `semantic_search` signature, append-only audit-row shape). The **real** proofs —
no-PII-to-public-tenant, tenant isolation under attack, audit-row completeness — run in the
**Phase-3 runtime gate** with adversarial RBAC/GDPR tests against the running multi-tenant stack.
