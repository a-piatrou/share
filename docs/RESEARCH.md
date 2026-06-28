# GHOSTWIRE Agentic SDLC — Research & Evidence Appendix

> Companion to [`PLAN.md`](PLAN.md). Every Claude / Claude Code / Anthropic-API fact below
> was verified against **live documentation** (WebFetch/WebSearch) by a 23-agent research
> workflow, per the source-discipline rule. Environment facts (`.env`, CLI version, scopes)
> were verified directly on this machine. Versions are pinned where stated by the source.

Verified environment: Claude Code **v2.1.193**, Agent SDK **0.3.187**, model Opus 4.8,
`/effort` **xhigh**, subscription OAuth (no Console key), official plugin marketplace
installed. `.env` is **0 bytes**.

---

## 1. Authorization: OAuth vs Console API key

The subscription OAuth token is **inference-scoped only** (doc, verbatim: *"scoped to
inference only and cannot establish Remote Control sessions"*). The Claude API REST surface
requires `x-api-key` (Console key) or a WIF Bearer token. Claude Code brokers subscription
inference for us; it does **not** turn the subscription into a general Console credential.

| Capability | Build time (our dev-agents, OAuth) | Needs Console API key | Notes |
|---|:---:|:---:|---|
| Messages inference (the harness's model calls) | ✅ | — | drawn from subscription when logged in via `/login` |
| Model selection (`/model`, frontmatter) | ✅ | — | available both ways |
| Prompt caching | ✅ | ✅ | request-level feature; rides on whatever does inference |
| Subagents / dynamic workflows / worktrees / hooks / skills / plugins | ✅ | — | harness mechanics; need only inference |
| File upload (`user:file_upload`) | ✅ | — | scope present |
| **Batch API** (Message Batches, −50%) | ❌ | ✅ | first-party endpoint; the *generated app* at runtime |
| **Files API** (`/v1/files`) | ❌ | ✅ | same |
| **`count_tokens` endpoint** | ❌ | ✅ | same (token counting *inside* harness inference still happens) |
| **Admin API** | ❌ | ✅ (`org:admin` scope) | not our scope; org administration |
| Server-side `task_budget` | ❌ | ✅ | **no token-budget lever under OAuth** — important |

**Limits.** Subscription = **~5-hour rolling window + weekly compute cap**, *shared* across
claude.ai chat, Desktop, and Claude Code — **not** RPM/TPM. The Console API (the generated
app's runtime) is RPM/ITPM/OTPM, token-bucket, tier-based. Consequence: we cannot
capacity-plan precisely; we watch `/usage` + `/status` reactively and keep concurrency bounded.

**Agent SDK is disqualified for build-time** (high confidence, verbatim): *"Anthropic does
not allow third party developers to offer claude.ai login or rate limits for their products,
including agents built on the Claude Agent SDK."* It requires a Console key. This is what
forces the native-harness substrate (see [`PLAN.md` §2](PLAN.md#2-architecture-decision-adversarial-verdict)).

---

## 2. Plugins, Skills, Hooks (verified mechanics)

**Plugin manifest** — `.claude-plugin/plugin.json`. Fields: `name` (req), `description`,
`displayName` (v2.1.143+), `version` (semver; else git SHA), `author`, `homepage`,
`repository`, `license`, `keywords`, path overrides (`skills`, `commands`, `agents`, `hooks`,
`mcpServers`), **`defaultEnabled`** (v2.1.154+). Component dirs live at the **plugin root**
(only `plugin.json` goes in `.claude-plugin/`).

**SKILL.md frontmatter — REAL fields:** `name`, `description`, `when_to_use`,
`argument-hint`, `arguments`, `disable-model-invocation`, `user-invocable`, `allowed-tools`,
`disallowed-tools`, `model`, `effort`, `context`, `agent`, `hooks`, `paths`, `shell`.
- ✅ `disallowed-tools` (least-privilege), ✅ `effort` (low…max).
- ❌ **`display-name`, `default-enabled`, `metadata.*` are NOT SKILL.md fields.** The label is
  `name`; `displayName`/`defaultEnabled` are **plugin.json** (camelCase) keys.

**Reload:** the command is **`/reload-plugins`** (reloads plugins/skills/agents/hooks/MCP/LSP).
There is **no `/reload-skills`**. Edits under watched skill dirs apply automatically in-session.
`SessionStart` hook → `hookSpecificOutput.reloadSkills: true` **is real** (picks up new skills).

**Hook events — all REAL** (verified): `PreToolUse`, `PostToolUse`, `SessionStart`, `Stop`,
`SubagentStop`, `SubagentStart`, `Notification`, **`TaskCompleted`**, **`TeammateIdle`**,
`TaskCreated`, plus `SessionEnd`, `UserPromptSubmit`, `PreCompact`/`PostCompact`,
`PostToolUseFailure`, `ConfigChange` (matcher includes `skills`), `WorktreeCreate/Remove`, etc.
`PreToolUse`/`Stop`/`SubagentStop`/`TaskCompleted` can **block** (gate "done"). This validates
the progress/gate-automation design.

**Subagents / orchestration mechanics:**
- Task tool was renamed **Agent** (v2.1.63; `Task(...)` aliases still work). Restrict spawnable
  types via `Agent(type1,type2)`.
- **Nested subagents** (v2.1.172+), depth limit **5**.
- **`isolation: worktree`** in frontmatter (or `Agent` tool / `claude --worktree`) — temp git
  worktree per writer, branched from `worktree.baseRef` (`head`|`fresh`), auto-cleaned if
  untouched. **Default base is `origin/HEAD`** → undefined here (no remote) → must set `head`.
- **`CLAUDE_CODE_SUBAGENT_MODEL`** sets the model for **ALL** subagents/teams, **overriding**
  per-invocation and frontmatter `model`. So it **cannot** mix cheap-worker + Opus-lead — use
  **per-agent `model` frontmatter** for that.
- **Dynamic workflows** (v2.1.154+): JS Claude writes; background runtime; up to **16
  concurrent / 1000 total**; intermediate results in script variables (out of context).
  Trigger keyword **`ultracode`** (was `workflow` pre-v2.1.160). Monitor: **`/workflows`**.
- **Agent teams**: EXPERIMENTAL, off by default (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`).
  No session resumption, one team/session, fixed lead → **reserved/avoided** for this build.

**Official plugins (installed locally) we'll use:** `frontend-design`, `commit-commands`,
`security-guidance` (PreToolUse guardrail), `pyright-lsp`, `typescript-lsp`, `hookify`,
`plugin-dev`. Held for later: `feature-dev`, `code-review`, `pr-review-toolkit`. **Skip
`agent-sdk-dev`** (SDK unavailable on OAuth).

> Caveat: `docs.claude.com/.../plugins` now redirects to `code.claude.com/docs/en/plugins`
> (canonical). Note the `agent({schema})` signature from the brief is **not** a documented
> *subagent* API — but it **is** the native **Workflow tool** API (used by this research run);
> the SDK's `outputFormat` json_schema path is the Console-key one.

---

## 3. Optimization toolkit (quality / speed / token economy)

`oauth` = usable by our dev-agents at build time under the subscription. `apikey` = a
first-party feature the **generated app** uses at runtime with a Console key (not reachable
through the subscription harness). `both` = a request-level feature available in either path.

| Technique | What it does / effect | Build-time (OAuth) | App-runtime (apikey) | Lever |
|---|---|:---:|:---:|---|
| **Prompt caching** | cache stable prefix; reads ~0.1×, writes 1.25×/2× (5m/1h). Min prefix: Opus 4.8/Sonnet 4.6 1024, Haiku 4.5 4096 | ✅ | ✅ | tokens + speed |
| **Multi-model routing** | Haiku→cheap, Sonnet→balanced, Opus→hard | ✅ via per-agent `model` | ✅ via model id per call | tokens + speed |
| **Effort control** | `output_config.effort` low…max (default high on Opus 4.8); `ultrathink`/`/effort` in harness | ✅ (`/effort`, frontmatter) | ✅ | tokens + quality |
| **Streaming** | SSE deltas; required for large `max_tokens` (>~16K; 128K needs it) | ✅ | ✅ | speed/UX |
| **Parallel tool use** | multiple `tool_use` in one msg; return all results in ONE user msg | ✅ | ✅ | speed |
| **Read-on-demand / no codebase dump** | load only needed files; smaller focused context | ✅ (core discipline) | ✅ | tokens + quality |
| **Truncate/summarize tool output** | cap/condense large results; or programmatic tool calling | ✅ | ✅ | tokens + quality |
| **Context editing** (`context-management-2025-06-27`) | server-side *clear* stale tool results/thinking | — | ✅ | tokens |
| **Compaction** (`compact-2026-01-12`) | server-side *summarize* near window limit | — | ✅ | tokens + quality |
| **Memory tool** (`memory_20250818`) | client-run cross-session `/memories` store | — | ✅ | quality |
| **Batch API** | async, **−50%**, ≤100k req/batch, <1h typical | — | ✅ | tokens (no latency win) |
| **Files API** (`files-api-2025-04-14`) | upload once, reference by `file_id` | — | ✅ | tokens |
| **Token counting** (`count_tokens`) | exact pre-send budgeting (never tiktoken) | — | ✅ | planning |
| **Task budgets** (`task-budgets-2026-03-13`) | model self-moderates to a token ceiling | — | ✅ (Opus 4.8/4.7/Fable) | tokens + graceful |

**Build-time levers we actually control (OAuth):** effort/`ultracode`, per-agent model
routing, parallel tool calls, streaming, read-on-demand, output truncation, prompt caching.
**App-runtime wins (Console key):** prompt caching first (highest leverage), Batch for bulk
+ 1h cache, the three context controls (editing/compaction/memory), task budgets, streaming.

**Models (verified):** Opus 4.8 `$5/$25` per MTok (1M ctx, 128K out); Sonnet 4.6 `$3/$15`
(1M, 64K); Haiku 4.5 `$1/$5` (200K, 64K).

---

## 4. Task normalization → contract

The normalizer parses the prose task **once** into `project_state.json` + committed contract
files; dev-agents never re-interpret prose. Proposed `project_state.json`:
`{ project_meta, requirements[], domain_model, interface_contracts, output_schemas,
acceptance_criteria[], module_ownership[], verify_loop, glossary }` plus the live ledger
fields `status_by_module`, `contract_version`, `verify_status_by_module`,
`open_contract_proposals[]`.

**The 4 non-negotiable shared interfaces (freeze first):**
`KnowledgeCore.semantic_search(query, domain_filter) -> RetrievedChunk[]`,
`EmbeddingService.embed(...)`, `EmployeeIntelligenceProfile`, `FeedbackIntelligence`.
Also frozen (the most-missed, per the devils): the **RBAC authorization-context** propagated
on every `semantic_search`, and the **append-only audit-row schema**
(`trace_id`, inputs hash, retrieved chunk IDs, prompt/model version, output, grounding score,
principal).

**Output schemas (committed JSON Schema, double as acceptance gates):**
- RAG answer: `{ answer, citations[] (≥1 when substantive; {source_id,snippet}), intent
  (client|candidate), confidence, abstained }`.
- Feedback: `{ strengths[], weaknesses[], risks[], team_dynamics_signals[], confidence_score }`
  with an `evidence_ref` per item.
- Team assembly: `{ team[] ({employee_id, role, match_score, feedback_signal_ref}), gaps[],
  risks[], alternatives[] }`.

**Acceptance criteria from the failure conditions (automatic-fail):**
AC-1 grounding — substantive answer ⇒ ≥1 citation resolving to a *real retrieved chunk*, else
`abstained=true`; AC-2 not-generic — each feedback item has `evidence_ref` (human/LLM-judge,
**not** a denylist — paraphrasable); AC-3 behavioral data — each team member has
`feedback_signal_ref`; AC-4 shared intelligence — **usage** (not just import) proven by the
corpus-mutation test at the runtime gate.

**Contract-first parallel:** one worktree per owner (`knowledge_core`, `chatbot`, `feedback`,
`team_assembler`, `frontend`); contracts are **read-only** to feature agents; a single
`contract` role is the only writer of OpenAPI/JSON-Schema/stubs/`contract_version`. A
`contract_version` bump signals dependents to re-pull + re-verify.

---

## 5. Architecture evaluation detail

Each pattern: Advocate thesis → devil verdict (all "viable-with-caveats" — none is a clean
win alone) → the top failure mode and the kill-condition. Full text in the workflow output.

- **single-loop** — *the four failure conditions are all about connectedness; one context
  keeps the "one brain" coherent.* Top failure: **context-window collapse of the "one brain"
  at module 3** (self-refuting). Kill: if the build can't be made checkpoint-resumable.
  → contributes the *durable contract files* as the fix.
- **orchestrator-worker** — *GHOSTWIRE's structure IS planner-freezes-contract +
  delegate-workers.* Top failure: **grounding is invisible to the orchestrator** (summary-only
  return). Kill: if the planner can't make the 4 conditions structurally checkable *before*
  delegation. → the harness execution shape we adopt.
- **pipeline-dag** — *GHOSTWIRE is a literal dependency graph; the "no shared intelligence"
  edge is what a DAG makes explicit.* Top failure: **semantic-vs-syntactic gap** (import ≠
  use). Kill: if per-node verify is treated as proof of the 4 conditions.
- **state-machine** — *explicit states + deterministic transition guards.* Top failure:
  **substrate conflation** (interactive hook-gated subagents ≠ a true dynamic workflow whose
  state lives in script variables). Kill: if built interactive, the window-survival thesis fails.
  → contributes the verify-loop as transition guards.
- **contract-first-parallel** — *freeze the small set of shared interfaces and the modules
  decouple.* Top failure: **semantic gap on the keystone condition**. Kill: **do not start
  parallel until the contract role RESOLVES (not guesses) vector-DB = Weaviate and the
  grounding/abstain threshold.** → the chosen primary decomposition.
- **reflection-critic** — *the conditions are structural, so generate→critique→revise fits.*
  Top failure: **equivocation** — the cheap deterministic verify-loop is *code*, not LLM
  reflection; the LLM-critic tier is the expensive part. Kill the LLM-critic tier if mean
  revise-iterations > 3 or no convergence within 5. → contributes the two-tier verify-loop.
- **native-claude-code** — *the OAuth constraint settles it; the SDK is disqualified.* Top
  failure: **summary-only return channel breaks contract fidelity** (lead never sees the diff).
  Kill: **if any `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` lands in `.env`/env it silently
  outranks the subscription** and misroutes billing. → the chosen substrate.

**Synthesis:** contract-first decomposition + bounded orchestrator-worker over a pipeline/DAG,
on the native dynamic-workflow + worktree substrate, with the verify-loop (from
reflection/state-machine) as the DoD and the durable contract files (from single-loop) as the
externalized "one brain". The unanimous devil's verdict — *build-time gates are syntactic,
the failure conditions are semantic* — makes the **runtime eval gate non-optional**.

---

## 6. Complementary stack on top of the mandatory stack

Mandatory (unchanged): FastAPI · React · Claude API · Weaviate/Pinecone · PostgreSQL · GCP.
Recommended complements (justification one-liners; pin exact patch versions at install):

- **Dep manager:** `uv` (fast, lockfile+venv+toolchain in one) — Poetry only as fallback.
- **DB:** `asyncpg` + **SQLAlchemy 2 async** (`postgresql+asyncpg://`, one `AsyncSession`/request,
  `expire_on_commit=False`) — holds the <2s RAG endpoint under concurrency.
- **Migrations:** **Alembic** (async `env.py`) — versioned/reviewable (audit NFR).
- **Validation/config:** **Pydantic v2** + `pydantic-settings` — also schema-validates every
  Claude response so malformed/ungrounded output fails fast.
- **Tests:** `pytest` + `pytest-asyncio` + `httpx.AsyncClient` + **testcontainers** (ephemeral
  Postgres + Weaviate).
- **Lint/types:** **Ruff** (lint+format) + **Pyright** (or mypy) — in pre-commit and CI.
- **Logging/tracing:** **structlog** (JSON) + **OpenTelemetry** → Cloud Trace/Logging; init
  OTel *before* structlog so `trace_id`/`span_id` is injected into every log — the **backbone
  of the AI-decision audit trail**. Model the RAG pipeline as explicit spans
  (retrieve → build-context → Claude → grounding-check).
- **RAG eval:** **Ragas** (faithfulness/groundedness) promoted into **DeepEval** as a CI gate;
  + a tracing/eval layer (Langfuse self-host) for live groundedness. Directly enforces "no
  hallucination."
- **Async work off the hot path:** **ARQ** (asyncio + Redis) — embedding/re-index, feedback
  batch, long team-scoring; keeps the chatbot's <2s SLA.
- **Frontend:** **Vite** + **TanStack Query** (+ Router) + **Tailwind** + **shadcn/ui** +
  TanStack Table (dashboards/candidate grids) + React Hook Form + **Zod** (client validation).
- **Vector DB — recommend Weaviate** (self-host on GKE in-VPC): native multi-tenancy
  (per-org/employee isolation), hybrid BM25+dense in one query, open-source — fits "no external
  exposure + GDPR + data residency". Pinecone weakens that posture (managed/external). *(Spec
  allows either — this is decision #3 in PLAN §11.)*
- **GCP mapping:** Cloud Run (2nd gen) for FastAPI (scale-to-zero) + Serverless VPC Access +
  Cloud SQL Auth Proxy (no public DB IP); **Cloud SQL Postgres** (private IP, PITR);
  **Memorystore Redis** (ARQ); **Secret Manager** (Claude key + DB creds); **Artifact
  Registry**; **Cloud Trace/Logging** (OTel sink).

**Grounding/explainability/audit at the architecture level:** context-only prompting with
per-claim citation IDs → automatic faithfulness judge that **refuses below threshold** rather
than answering → Pydantic-validated structured output carrying evidence (Explainability
Engine) → append-only AI-decision audit table keyed by `trace_id`. **RBAC defense-in-depth:**
enforce at the FastAPI dependency layer **and** map principals to Weaviate tenants so
*retrieval itself* cannot return unauthorized employee data; public chatbot on a **PII-free
tenant**.

---

## 7. Key fact corrections vs the original brief

| Brief said | Verified reality |
|---|---|
| token is in `.env` | `.env` is **0 bytes** — no token; session runs on subscription OAuth |
| `/reload-skills` | **does not exist** → `/reload-plugins`; auto-reload of watched dirs; `SessionStart→reloadSkills:true` is real |
| SKILL.md `display-name`, `default-enabled`, `metadata.*` | **not** SKILL.md fields → use `name`; `displayName`/`defaultEnabled` are **plugin.json** keys |
| `CLAUDE_CODE_SUBAGENT_MODEL` to mix cheap workers + Opus lead | it overrides **all** subagents incl. frontmatter → use **per-agent `model` frontmatter** to mix |
| `agent({schema})` as a subagent feature | it's the **Workflow tool** API (real, used here); SDK `outputFormat` is the Console-key path |
| Agent SDK as a candidate substrate | **disqualified at build time** — requires Console key, forbids claude.ai auth |
| Batch API "−50%, async — check under OAuth" | **Console-key only**; not reachable via subscription harness — it's a *runtime app* feature |
