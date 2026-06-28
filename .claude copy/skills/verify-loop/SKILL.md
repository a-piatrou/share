---
name: verify-loop
description: The two-tier verify-loop that defines "done" for any module a dev-agent builds in GHOSTWIRE. Use before reporting a module/worktree complete, and whenever deciding whether work is finished. A module is NOT done until tier-1 is green AND its acceptance checks pass.
---

# Verify-loop = definition of done

A worker may **not** report "done" until **tier-1 is green** AND the module's
`acceptance_criteria` checks pass. The `SubagentStop` / `TaskCompleted` hooks enforce this by
blocking completion when `verify` is not green. Run `make verify` (the single entrypoint) in
the worktree; loop fix → rerun until green, under a **hard per-node attempt cap**.

## Tier 1 — deterministic (drives ~all revisions; free & fast)
Order matters (cheapest first; stop at first failure, fix, rerun):
1. **compile / typecheck** — `python -m py_compile` or `mypy`/`pyright`; `tsc` for React.
2. **lint** — `ruff check` (+ `ruff format --check`); `eslint` for frontend.
3. **contract-validate** — module outputs validate against the committed JSON Schemas
   (`jsonschema`); the HTTP surface matches the frozen OpenAPI (`schemathesis`).
4. **boot** — the service starts (uvicorn boots; the app imports cleanly; docker build ok).
5. **smoke** — minimal request/response works (health endpoint; one happy-path call;
   for a feature module, one call against the **real** Knowledge Core, not just the stub).

## Tier 2 — semantic critic (expensive; GATED)
Only invoke **after tier-1 is green**, and only where correctness is semantic:
- An LLM/judge review of grounding, non-genericness, or rationale quality.
- **Hard attempt cap (e.g. 5)** with **best-so-far checkpointing**; there is no server-side
  `task_budget` under the build OAuth token, so a non-converging loop silently drains the
  weekly cap. If a node exceeds its cap → stop that node, checkpoint, let siblings proceed,
  and surface it (do not let one stuck node block the whole build).
- If a module's mean revise-iterations-to-green exceeds ~3, drop the LLM-critic tier for it
  and keep only the deterministic gate (treat grounding as a monitored metric, not a blocking
  gate that can flip across a window boundary and break resumability).

## What the deterministic gate CANNOT prove (escalate to the runtime gate)
Tier-1 is **syntactic** — it proves shape, compile, boot. It **cannot** prove the four
GHOSTWIRE failure conditions, which are **semantic/runtime**:
- does the chatbot actually **ground** (AC-1) — needs real retrieval + a faithfulness judge;
- is feedback actually **non-generic** (AC-2) — judge, not denylist;
- does the team score actually **move with behavioral data** (AC-3) — corpus-mutation test;
- do modules actually **use** the one brain at runtime (AC-4) — corpus-mutation test, not import-presence.

These run in the **Phase-3 runtime gate** on the app's own credential against a seeded corpus.
**A green build-time verify is necessary, NOT sufficient.** Never report the four conditions
satisfied on the basis of tier-1 alone.

## Resumability
Commit per green node (`git commit` with the module id + verify status), and patch
`project_state.json` (`status`, `verify_status`, `last_commit`). An OAuth-window interruption
is then a **pause** that resumes from disk, not a cold restart.
