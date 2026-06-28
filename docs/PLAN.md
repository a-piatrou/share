# GHOSTWIRE Agentic SDLC — Dev-Layer Plan (for approval)

> Status: **PROPOSAL — awaiting GO.** No system code is written yet. This document plus
> [`RESEARCH.md`](RESEARCH.md) is the deliverable to review. Every Claude/Claude-Code fact
> here was verified against live documentation by a 23-agent research workflow
> (`ghostwire-arch-research`), not from model memory.

---

## 0. TL;DR

- **We build the dev-agent layer ON the native Claude Code harness** (dynamic workflows +
  subagents + `isolation: worktree` + hooks). This is **forced, not chosen**: the Claude
  Agent SDK requires a Console API key and is explicitly **not allowed to authenticate with
  a subscription/claude.ai OAuth token** — and OAuth is the only credential we have.
- **Architecture = contract-first parallel build, executed as a bounded orchestrator-worker
  DAG, with a thin deterministic state/contract layer on disk** (`project_state.json` +
  `openapi.yaml` + `schemas/*.json` + frozen interface stubs) as the single source of truth,
  a two-tier per-worktree **verify-loop** as the definition-of-done, and a **mandatory
  runtime semantic/RBAC gate** that runs on the *generated app's own Console key*.
- **The binding constraint is the OAuth rolling window** (5h + weekly cap, shared with
  claude.ai/Desktop). So: bounded concurrency (~3–5 live workers), cheaper models for
  mechanical work, `commit-per-green-node` so an interruption is a *pause* (resume from
  disk), never a cold restart.
- **The decisive risk, raised unanimously by the adversarial pass:** every build-time gate
  is *syntactic* (does the field exist, does it import the core) while all four GHOSTWIRE
  failure conditions are *semantic* (does it actually ground? does the score actually move
  with behavioral data?). Therefore a runtime eval gate on a Console key is **non-optional**.
- **The three Phase-B decisions are resolved** (§11): app is credential-agnostic and uses the
  provided OAuth token for the local demo (Console key = drop-in production path); target is
  local **docker-compose** (GCP as Terraform artifacts); vector DB is **Weaviate**.

---

## 1. Authorization reality (what this token can and cannot do)

Full report + evidence in [`RESEARCH.md` §1](RESEARCH.md#1-authorization-oauth-vs-console-api-key).
Summary:

- The session runs on a **subscription OAuth token**, scoped **inference-only**
  (`user:inference`, `user:file_upload`, `user:profile`, `user:sessions:claude_code`).
  **`.env` now contains `CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01…`** — a *subscription OAuth*
  token (the build-time authorization credential), **not** a Console API key (`sk-ant-api…`).
  It is inference-only and draws from the shared 5h/weekly subscription window. A repo `.env`
  is not auto-loaded into the Claude Code process, so it does not misroute our session; it is
  available for the **generated app** to read at runtime.
- **Available to our dev-agents at build time (OAuth):** Claude model inference, model
  selection, prompt caching (it is a request-level feature), the entire Claude Code harness
  (subagents, dynamic workflows, worktrees, hooks, skills, plugins), file upload.
- **Requires a Console API key (NOT reachable via the subscription) — these belong to the
  *generated app* at runtime, not to us at build time:** Batch API, Files API, the standalone
  `count_tokens` endpoint, Admin API.
- **Limits are rolling-window, not RPM/TPM:** ~5-hour rolling session window + a weekly
  compute cap, **shared** across claude.ai chat, Desktop, and Claude Code. There is no
  per-minute throttle to absorb a burst and **no server-side `task_budget`** under OAuth
  (it is Console-key-gated). This is the single most important operational fact for budgeting.

**Build/runtime credential split (must stay strict):**

| | Build time (Phase A & B, our dev-agents) | Runtime (the generated GHOSTWIRE app) |
|---|---|---|
| Credential | Subscription OAuth (this session) | Its own **Console API key** (`ANTHROPIC_API_KEY`) |
| Limits | 5h rolling + weekly cap (shared) | RPM / ITPM / OTPM (tier-based) |
| Can use | inference, caching, harness, worktrees | + Batch, Files, count_tokens, task budgets |

> ⚠️ **Credential foot-gun:** if anyone ever sets `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN`
> in `.env` or the environment, it **silently outranks** the subscription and routes all
> build spend (every verify-loop call) to that key's org. We gate every long run behind a
> `/status` check and keep build-time `.env` clean of API keys.

---

## 2. Architecture decision (adversarial verdict)

Seven orchestration patterns were each defended by an **Advocate** and stress-tested by a
**Consul / devil's-advocate**; the key fork (native harness vs custom orchestrator) was a
3-agent debate with a synthesizing judge. Per-pattern verdicts and the full reasoning are in
[`RESEARCH.md` §5](RESEARCH.md#5-architecture-evaluation-detail).

### 2.1 The fork verdict: native substrate (forced)

> *Native Claude Code orchestration is the substrate — and under the subscription-OAuth
> constraint this is forced, not chosen. The Agent SDK requires a Console API key and
> Anthropic explicitly forbids claude.ai/subscription auth for SDK-built agents. We are
> already inside the harness with dynamic workflows (verified on v2.1.193), worktree
> isolation, `/workflows` monitoring and hooks — all running on the inference-scoped OAuth
> token that is the only credential we have.*

The genuine, valuable kernel of the "custom orchestrator" side — **deterministic
`contract_version` synchronization, schema-level automatic-fail gates, and a
disk-checkpointed `project_state.json`** — is *absorbed* as a thin deterministic layer **on
top of** native primitives. We do **not** build a bespoke orchestration runtime, retry
plumbing, or monitoring; `/workflows`, hooks and worktree isolation are battle-tested config,
not code we own and must debug.

### 2.2 Why this hybrid (and not single-loop / pure-reflection)

All five "serious" patterns independently re-derived the **same topology** — freeze the
shared interfaces first, build the Knowledge Core, fan out the modules in isolated worktrees
against frozen stubs, then integrate. That convergence is the strongest signal in the data,
and it matches the spec's own words: *"One brain, multiple interfaces."* Single-loop's real
strength (the shared "one brain" authored in one context) degrades exactly at module 3 when
the contract is compacted out of the window — the **contract artifact files are the fix**,
externalizing that brain as durable, re-readable source-of-truth. Reflection's real
contribution is the **verify-loop DoD** itself, which we adopt per worktree.

---

## 3. Dev-agent topology

```
PHASE 0  Contract Freeze            (serial, 1 "contract-lead", Opus 4.8 @ xhigh, REVIEWED)
  parse initial-ghostwire-task-description.md  ──►  project_state.json
                                                    openapi.yaml
                                                    schemas/{rag_answer,feedback_analysis,team_assembly}.json
                                                    stubs for the 4 shared interfaces
                                                    RBAC auth-context contract + append-only audit-row schema
  gate: schemas validate + stubs typecheck + HUMAN/2nd-agent review  ── before any fan-out

PHASE 1  Knowledge Core root        (serial — it is the critical path of 3 of 4 modules)
  real semantic_search/embed over Weaviate(multi-tenant) + Postgres, committed to base branch
  gate: verify-loop green

PHASE 2  Bounded fan-out            (parallel, isolation:worktree, ~3–5 live workers)
  ┌─ chatbot (Opus 4.8 — grounding-critical) ─┐
  ├─ feedback                                  ├─ each owns ONE worktree, contracts READ-ONLY
  ├─ team_assembler (scaffold) ◄── depends on ─┘ feedback's FeedbackIntelligence (the one real cross-edge)
  └─ frontend
  per-worker: per-worktree two-tier verify-loop (see §4)

PHASE 3  Integration join + RUNTIME gate   (the non-negotiable addition)
  lead RE-RUNS full verify on the actually-merged tree (never trust worker summaries)
  then a SEPARATE runtime gate on the app's OWN Console key against a seeded corpus:
    (1) faithfulness/groundedness eval + citation-resolution  (upgrades AC-1)
    (2) corpus-mutation behavioral test: mutate data → assert answers/scores CHANGE  (proves AC-3, AC-4)
    (3) adversarial RBAC / tenant-isolation / no-PII-to-public-tenant + audit-row completeness
```

**Deterministic state layer (the surviving "custom orchestrator" value):**
`project_state.json` on disk is the durable ledger (`status_by_module`, `contract_version`,
`verify_status_by_module`, `open_contract_proposals`). **Commit-per-green-node** so a
window/cap interruption resumes from disk. `contract_version` is the monotonic re-arm signal;
a bump forces dependent worktrees to re-pull and re-verify. **Kill-switch:** if
`contract_version` bumps exceed ~2–3, the freeze was a fiction → collapse to a serial
Knowledge-Core-first build.

---

## 4. Verify-loop = definition of done (two-tier)

A worker may **not** report "done" until verify is green **and** its module's acceptance
checks pass. Wired via `SubagentStop` / `TaskCompleted` hooks that **block** completion;
hooks and schemas are owned by the contract-lead (an agent that can edit its own gate can
weaken it).

- **Tier 1 — deterministic (drives ~all revisions, free/fast):**
  `compile → typecheck (ruff/mypy or pyright; tsc) → lint → contract-validate
  (jsonschema + schemathesis vs frozen OpenAPI) → boot → smoke`.
- **Tier 2 — semantic critic (expensive, gated):** only invoked *behind* a deterministic-green
  precondition, with a **hard per-node attempt cap (e.g. 5)** and best-so-far checkpointing —
  because there is no server-side `task_budget` under OAuth and a non-converging loop silently
  drains the weekly cap.

The four GHOSTWIRE failure conditions become **structural acceptance checks** (see
[`RESEARCH.md` §4](RESEARCH.md#4-task-normalization--contract)): required `citations[]` on RAG
answers (anti-hallucination), required `evidence_ref` per feedback item (anti-generic),
required `feedback_signal_ref` per team member (forces behavioral data), and a shared-core
**usage** check (not just import-presence) verified at the runtime gate.

---

## 5. Cross-cutting NFR ownership (the devils' catch)

One-worktree-per-module assigns **no owner** to RBAC, append-only audit, and
no-PII-to-public-tenant — yet these span every module and isolation prevents convergence.
**Mitigation:** lift RBAC/audit into a **single shared-owned library** (`shared/security`)
that every module consumes; freeze its contract in Phase 0; test it adversarially in the
Phase-3 runtime gate. *A green build that ships PII to the public chatbot tenant is worse
than no automation — it manufactures false confidence on the highest-severity requirement.*

---

## 6. Phase A — build the system (what we author)

Phase A is lightweight (authoring config + small tools), not a big fan-out. Deliverables, all
under project `.claude/` (packaged as a local plugin `ghostwire-sdlc` so it is portable):

1. **`project_state.json` schema + `task-normalizer` skill** — parse the prose task **once**
   into `project_state.json` + committed contracts; dev-agents never re-interpret prose.
2. **Skills** (`.claude/skills/<name>/SKILL.md`, correct frontmatter — see note below):
   - `task-normalizer` — prose → contract.
   - `stack-conventions` — the GHOSTWIRE complementary stack & idioms ([`RESEARCH.md` §3](RESEARCH.md#3-complementary-stack-on-top-of-the-mandatory-stack)).
   - `verify-loop` — how to run the two-tier gate; ships a single `make verify` per worktree.
   - `ghostwire-schemas` — the three output schemas + the automatic-fail acceptance criteria.
   - `gdpr-rbac-guardrail` — GDPR/RBAC/audit conventions + the shared `security` library contract.
   - Reuse built-ins: **`claude-api`** (correct Claude SDK code on Opus 4.8) and **`frontend-design`** (React UI).
3. **Subagent definitions** (`.claude/agents/*.md`, least-privilege tools, per-agent `model`
   frontmatter, `isolation: worktree` for the writers): `contract-lead`,
   `knowledge-core-builder`, `chatbot-builder` (Opus 4.8), `feedback-builder`,
   `team-assembler-builder`, `frontend-builder`, `integration-verifier`.
4. **Hooks** (`.claude/hooks/hooks.json`): `SessionStart`→`reloadSkills:true` (pick up new
   skills mid-session); `SubagentStop`/`TaskCompleted`→block "done" until verify green;
   `Stop`/`PostToolUse`→append progress to `PROGRESS.md`.
5. **Orchestration**: the Phase 0→3 topology as a **dynamic-workflow script** (driven via
   `ultracode`, monitored via `/workflows`) for the fan-out, with the deterministic
   contract/state layer (`project_state.json`, `contract_version`, commit-per-green-node) as
   files the lead manages. Bounded concurrency dialed to ~3–5.
6. **`worktree.baseRef: "head"`** set explicitly in settings (this repo has **no remote /
   `origin/HEAD`** — worktree isolation defaults to `origin/HEAD` and would be undefined).

> **Fact corrections baked in (from research, vs the original brief):**
> `/reload-skills` does **not** exist → use `/reload-plugins` (or rely on auto-reload of
> watched skill dirs); `SessionStart`→`reloadSkills:true` is real. `display-name` /
> `default-enabled` / `metadata.*` are **not** SKILL.md fields — the real fields are `name`,
> `description`, `when_to_use`, `allowed-tools`, `disallowed-tools`, `model`, `effort`,
> `context`, `agent`, `hooks`, `paths`; `displayName`/`defaultEnabled` are **plugin.json**
> (camelCase) keys. `CLAUDE_CODE_SUBAGENT_MODEL` overrides **all** subagents incl.
> frontmatter — so to mix a cheap-worker + Opus-lead we use **per-agent `model` frontmatter**,
> not that env var. Schema-validated subagent output is native to the **Workflow tool**
> (`agent(prompt, {schema})`, which this very research run used) — the SDK `outputFormat`
> path is the one that needs a Console key.

---

## 7. Phase B — generate & bring up GHOSTWIRE

Runs the system from Phase A. Step sequence mirrors §3:

1. **Phase 0** — contract-lead normalizes the task → `project_state.json` + `openapi.yaml` +
   `schemas/*.json` + shared stubs + RBAC/audit contracts. **Stop for review** (front-loading
   all schema risk into one unreviewed parse is the most expensive failure mode).
2. **Phase 1** — build the real Knowledge Core (Weaviate + Postgres), commit to base.
3. **Phase 2** — bounded worktree fan-out: chatbot, feedback, team_assembler(scaffold),
   frontend; release team_assembler scoring only after feedback is green.
4. **Phase 3** — lead re-verifies the merged tree, then the **runtime semantic/RBAC gate**.
5. **Bring-up** — `docker-compose up` (Postgres + Weaviate + FastAPI + React) with health +
   smoke; seed a small corpus; confirm the RAG endpoint answers grounded-or-abstains in <2s.

**Runtime Claude credential (resolved):** steps 4–5's *semantic* gates require the app to call
Claude at runtime. The app's Claude client is **credential-agnostic** — it reads
`ANTHROPIC_API_KEY` (Console) or `ANTHROPIC_AUTH_TOKEN` (OAuth `Authorization: Bearer` +
`anthropic-beta: oauth-2025-04-20`). For the local demo it uses the OAuth token already in
`.env`, so RAG genuinely answers and the grounding gate is real; a Console key added later is a
zero-code-change upgrade. Because these runtime calls share the subscription window, the
seeded eval corpus and query count stay small.

---

## 8. Parallelism & token-budget policy (OAuth-aware)

- **Fan out only on genuinely independent work** — the modules are; the contract freeze and
  Knowledge Core are serial bottlenecks, not peers.
- **Bounded concurrency ~3–5** live workers (well below the 16-agent workflow ceiling) to
  protect the rolling window.
- **Model routing by cost:** Opus 4.8 @ xhigh for the contract-lead + grounding-critical
  chatbot only; route mechanical workers to Sonnet 4.6 / Haiku 4.5 via **per-agent
  frontmatter** (not the global env var). Prices: Opus 4.8 `$5/$25`, Sonnet 4.6 `$3/$15`,
  Haiku 4.5 `$1/$5` per MTok.
- **Commit-per-green-node** → interruption = pause, not restart.
- **Reactively watch `/usage` and `/status`**; reduce concurrency toward serial as the
  weekly cap approaches (it is a live dial, not a fixed setting). Reserve experimental
  **agent-teams entirely** — no session resumption; subagents + dynamic workflows are safer.

---

## 9. Observability & progress (per task §8)

- **`PROGRESS.md`** (English, in repo) is the source of truth: stages + tasks with status
  (`todo`/`in-progress`/`done`/`failed`) and what remains. Updated automatically by **hooks**
  (`Stop`, `PostToolUse`, `SubagentStop`/`TaskCompleted`).
- **Chat updates (Russian)** at every stage boundary: "stage N of M, what's running, tasks
  done/left, which agents finished/failed" — counters, not fake ETAs.
- **`/workflows`** for live fan-out monitoring; periodic **`/usage`** reports so you see the
  window headroom.
- A short **stage-boundary summary**: done / next / decisions needed.

---

## 10. Plugins & skills (use vs create)

Detail + justification in [`RESEARCH.md` §2](RESEARCH.md#2-plugins-skills-hooks). Summary:

**Enable (official marketplace, already installed locally):**
`frontend-design` (React UI, auto-invokes), `commit-commands` (git/commit/PR),
`security-guidance` (PreToolUse guardrail — fits GDPR/RBAC), `pyright-lsp` + `typescript-lsp`
(fast typecheck for the verify-loop), `hookify` (author our progress/gate hooks),
`plugin-dev` (package `ghostwire-sdlc`). `feature-dev` and `code-review`/`pr-review-toolkit`
held for later (review stage is out of scope now). **Not** `agent-sdk-dev` — the SDK path is
unavailable on OAuth.

**Create (this plan):** the `ghostwire-sdlc` plugin bundling the skills, agents, and hooks in
§6. Third-party/community plugins treated as untrusted — none added without explicit reason.

---

## 11. Decisions — RESOLVED

1. **Runtime Claude credential for the app → credential-agnostic, OAuth token for the local
   demo.** `.env` provides a subscription OAuth token (`CLAUDE_CODE_OAUTH_TOKEN`), not a
   Console key. The app's Claude client reads **either** `ANTHROPIC_API_KEY` (Console,
   `x-api-key`) **or** `ANTHROPIC_AUTH_TOKEN` (OAuth `Authorization: Bearer` +
   `anthropic-beta: oauth-2025-04-20`) from env; for the local demo it defaults to the
   provided OAuth token so RAG actually answers and the semantic gate is real. A Console key
   dropped in later is picked up with **zero code change** (production path). *Budget caveat:*
   the app's runtime calls share the same subscription window as the build → keep the seeded
   eval corpus and query count small.
2. **Deployment target → local `docker-compose`** (Postgres + Weaviate + FastAPI + React),
   health/smoke/<2s RAG. GCP is authored as **Terraform/IaC artifacts**, not deployed (no GCP
   creds).
3. **Vector DB → Weaviate** (self-hosted, in-VPC, native multi-tenancy) — fits the
   "no external exposure + GDPR + data residency" NFR.

---

## 12. Top risks (from the adversarial pass) & mitigations

| Risk | Mitigation |
|---|---|
| **OAuth window burn** (binding) | bounded concurrency, cheap-model routing, commit-per-green-node, watch `/usage` |
| **Syntactic-vs-semantic gate gap** (unanimous) | mandatory Phase-3 runtime gate with corpus-mutation + citation-resolution |
| **Contract freeze = single point of catastrophe** | human/2nd-agent review before fan-out; freeze RBAC+audit too |
| **Worktree baseRef undefined** (no remote) | set `worktree.baseRef:"head"`; commit stubs+core to base before fan-out |
| **Stub-vs-real divergence at integration** | build Knowledge Core real & first; reach real-retrieval smoke; lead re-verifies merged tree |
| **Cross-cutting NFRs have no owner** | shared `security` library, frozen in Phase 0, adversarially tested at runtime gate |
| **Verify-loop non-convergence / token blowup** | hard per-node attempt cap + best-so-far; gate critic behind deterministic-green |
| **Credential silent misroute** | `/status` check + keep `.env` free of API keys before every run |

---

## 13. What happens after GO

1. Phase A: author the `ghostwire-sdlc` plugin (skills, agents, hooks), `project_state.json`
   schema, the `verify` command, `worktree.baseRef`, and `PROGRESS.md`; enable the chosen
   plugins; reload.
2. Phase B: run the workflow — Phase 0 (freeze, **pause for your review**) → 1 → 2 → 3 →
   bring-up — with live Russian stage updates and `PROGRESS.md` kept current, until a working
   GHOSTWIRE MVP is up.
