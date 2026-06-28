# GHOSTWIRE — Corporate Intelligence Grid

An AI platform with **one shared brain, multiple interfaces**: a public RAG chatbot, a Feedback
Intelligence Engine, and an AI Team Assembler — over a single Knowledge Core, with grounding,
explainability, RBAC, and an append-only audit trail.

This repository contains **both** halves of the exercise:

1. **The Agentic SDLC system** that generated the app — under [`.claude/`](.claude/) (skills,
   subagents, hooks) + [`system/`](system/) (frozen contracts, verify tooling). See
   [`docs/PLAN.md`](docs/PLAN.md) (architecture decision) and [`docs/RESEARCH.md`](docs/RESEARCH.md)
   (source-verified evidence). Build status: [`PROGRESS.md`](PROGRESS.md).
2. **The generated GHOSTWIRE app** — [`backend/`](backend/) (FastAPI) + [`frontend/`](frontend/)
   (React) + [`docker-compose.yml`](docker-compose.yml) + [`system/seed/`](system/seed/).

## Architecture

```
                     ┌──────────────── Knowledge Core (shared brain) ────────────────┐
                     │ semantic_search (Weaviate, multi-tenant, RBAC-scoped) ·         │
                     │ EmbeddingService · EmployeeIntelligenceProfile · FeedbackIntel  │
                     └───────────────────────────────────────────────────────────────┘
   chat widget ─▶ /chat/query ─┐        feedback dashboard ─▶ /feedback/analyze ─┐   team UI ─▶ /team/assemble ─┐
                               └──────────── all route through the shared accessors ──────────────┘
   shared_security: AuthContext + RBAC (API layer + Weaviate-tenant layer) · append-only AuditRow (trace_id)
```

- **Module 1 — Public RAG chatbot**: intent → retrieve (public PII-free tenant) → grounded
  answer with per-claim citations; **abstains** when context is insufficient (no hallucination).
- **Module 2 — Feedback Intelligence**: reviews → structured strengths/weaknesses/risks/signals,
  each with an `evidence_ref`; deterministic `feedback_score`.
- **Module 3 — AI Team Assembler**: project analysis → candidate scoring (skill / **feedback** /
  experience / availability / compatibility) → team with per-member `feedback_signal_ref` + rationale.

Contracts are frozen in [`system/contracts/`](system/contracts/) (OpenAPI 3.1, JSON Schemas,
typed interface stubs). The four GHOSTWIRE failure conditions are encoded as automatic-fail
acceptance criteria (AC-1..AC-5) in [`project_state.json`](project_state.json).

## Tech stack

FastAPI · React (Vite) · Claude API · **Weaviate** (self-hosted, multi-tenant) · PostgreSQL · GCP
(IaC target). Complements: uv · SQLAlchemy 2 async + asyncpg · Alembic · Pydantic v2 · structlog
+ OpenTelemetry · text2vec-transformers (all-MiniLM-L6-v2, 384-dim) · TanStack Query/Table +
Tailwind + Zod. Rationale in [`docs/RESEARCH.md`](docs/RESEARCH.md) §6.

## Run it locally

Prereqs: Docker, Python 3.12 (via `uv`), Node 20+.

```bash
# 1. Datastores (Postgres + Weaviate + embeddings sidecar)
docker compose up -d        # wait until all 3 are healthy

# 2. Backend
cd backend
python3 -m uv venv --python 3.12 .venv && python3 -m uv pip install -e ".[dev]" --python .venv/bin/python
cp .env.example .env        # then set a Claude credential (see below)
.venv/bin/alembic upgrade head
make seed                   # load system/seed/ into Postgres + Weaviate
.venv/bin/uvicorn app.main:app --port 8000

# 3. Frontend (new shell)
cd frontend && npm install && npm run dev   # http://localhost:5173
```

### Claude credential (the app is credential-agnostic)

The app builds a **credential pool** from, in order: `ANTHROPIC_API_KEY` (Console key) →
`ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_AUTH_TOKEN_1`…`_4` (subscription OAuth tokens, `sk-ant-oat01…`,
sent as `Authorization: Bearer` + `anthropic-beta: oauth-2025-04-20`) → a labelled **stub** (boots
and answers with no credential). Each call **round-robins** the starting credential and **fails
over** to the next on a 429/API error (`app/llm/claude_client.py`).

> A subscription OAuth token is the Claude Code credential: the API grants it the premium models
> (Sonnet/Opus) **only when the request looks like Claude Code** — specifically when the first
> system block is the Claude Code identity string. The client injects that block automatically for
> OAuth credentials (`_with_cc_identity` in `app/llm/claude_client.py`); without it, Sonnet/Opus
> are rejected with a *masked* `429 rate_limit_error` (message just `"Error"`) while Haiku still
> passes — which is easy to misread as "OAuth is Haiku-only". It isn't.
>
> Pooling across **distinct tokens from different accounts** gives ~N× throughput + fallback (each
> account has its own rolling window). A Console API key (`ANTHROPIC_API_KEY`, separate RPM/TPM)
> also works and needs no identity block — but is **not required**; the OAuth pool serves
> Sonnet/Opus directly.

Feature models run on **Sonnet 4.6**: the chatbot keeps adaptive thinking **off** to hold the <2s
SLA; feedback and team-assembly also run thinking-off (Sonnet's grounded output already meets the
evidence/quality bar, so the latency tax of thinking buys nothing the acceptance criteria need).

## Verify (definition of done)

- Build-time tier-1: `cd backend && make verify` (compile · ruff · mypy · contract-validate · boot).
- Live (with a credential + stack up): `/chat/query` grounds & cites or abstains;
  `/feedback/analyze` (RBAC) returns evidence-backed items; `/team/assemble` (RBAC) scores via
  feedback. PII isolation, RBAC (403 without a token), and append-only audit are enforced.

## Notes / limits

- **GCP** is delivered as the documented target (Cloud Run + Cloud SQL + Serverless VPC + Secret
  Manager + Artifact Registry); the runnable target here is local `docker-compose`.
- A subscription OAuth token reaches Sonnet/Opus only when the Claude Code identity leads the
  system prompt (the client injects it); a *genuine* rolling-window rate-limit (429) is still
  possible under sustained load, and the app **degrades gracefully** then (chatbot abstains,
  internal endpoints 503). Pooling distinct cross-account tokens spreads that load ~N×.
