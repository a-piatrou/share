---
name: task-normalizer
description: Procedure to normalize a prose app spec ONCE into machine-readable contracts that dev-agents act on. Use at Phase 0 (contract freeze) to turn the task description into project_state.json + a committed OpenAPI doc + output schemas + frozen interface stubs. General to any app; tuned defaults for GHOSTWIRE.
---

# Task normalizer (Phase 0 — contract freeze)

Parse the prose spec **exactly once** into committed contract artifacts; dev-agents then read
**only** these — never re-interpret prose. This removes the largest source of parallel-writer
drift. Front-loading all schema risk into one unreviewed parse is the most expensive failure
mode, so the frozen contract is **reviewed before any fan-out**.

## Inputs
- The prose spec (for GHOSTWIRE: `initial-ghostwire-task-description.md`).
- Resolved decisions from `docs/PLAN.md` §11 (target=`local-docker-compose`, vector_db=`weaviate`,
  credential-agnostic Claude client).

## Output artifacts (all committed to the base branch)
1. **`project_state.json`** — conforms to `system/contracts/project_state.schema.json`. The
   single source of truth + live ledger. Fill: `project_meta`, `requirements[]` (atomic,
   id'd, with `source_quote`), `modules[]` (id/owner/depends_on/status=planned),
   `interface_contracts`, `output_schemas` (point at the schema files), `acceptance_criteria[]`
   (the AC-1..AC-5 from `ghostwire-schemas`), `verify` (command + tier1/tier2 steps), `glossary`.
2. **`openapi.yaml`** — OpenAPI 3.1 for every cross-module HTTP boundary (chatbot, feedback,
   team, health).
3. **Output schemas** — already authored under `system/contracts/schemas/`; reference them.
4. **Shared interface stubs** — Python stubs (signatures only, typed) for the four shared
   interfaces so all feature worktrees compile against identical signatures from minute one:
   `KnowledgeCore.semantic_search(query, domain_filter, auth_ctx) -> list[RetrievedChunk]`,
   `EmbeddingService.embed(texts) -> list[Vector]`, `EmployeeIntelligenceProfile`,
   `FeedbackIntelligence`.
5. **Cross-cutting contracts (most-missed — freeze these too):** the **RBAC `AuthContext`**
   propagated on every `semantic_search`, and the **append-only `AuditRow`** schema
   (`trace_id`, inputs hash, retrieved chunk ids, prompt/model version, output, grounding
   score, principal). See `gdpr-rbac-guardrail`.

## RESOLVE before freeze (do not guess)
- Vector DB = **Weaviate** (decided). Grounding/abstention **threshold** and abstain semantics
  — pick an explicit number and behavior. RBAC tenant model (public chatbot on a PII-free
  tenant). These are contract-level and must be pinned, not left to feature agents.

## Gate
Schemas validate; stubs typecheck; OpenAPI is well-formed. **Then STOP for human/second-agent
review** before Phase 1. A contract defect multiplied across 4–5 writers only surfaces at the
integration join, after maximum spend.

## During the build
`contract_version` starts at 1 after freeze. Only the **contract-lead** edits contracts; a
change bumps `contract_version`, forcing dependent modules to re-pull + re-verify. If bumps
exceed ~2–3, the freeze was a fiction → collapse to a serial Knowledge-Core-first build.
