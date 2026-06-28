---
name: stack-conventions
description: GHOSTWIRE application tech-stack conventions and idioms (FastAPI + React + Claude + Weaviate + PostgreSQL + GCP, plus the chosen complements). Use when scaffolding or writing any backend/frontend code, the Claude client, the data layer, async work, tests, or the docker-compose/IaC for the GHOSTWIRE app. Do NOT replace the mandatory stack; these are complements on top of it.
---

# GHOSTWIRE stack conventions

Mandatory (never replace): **FastAPI · React · Claude API · Weaviate · PostgreSQL · GCP.**
Chosen complements (rationale in `docs/RESEARCH.md` §6). Pin exact patch versions at install
(verify current versions with the `claude-api` skill / WebSearch — these move fast).

## Backend (Python)
- **uv** for deps/venv/lockfile. `pyproject.toml`, `uv.lock` committed.
- **FastAPI** app factory; routers per module (`chatbot`, `feedback`, `team`, `health`).
- **Pydantic v2** for all request/response models + **pydantic-settings** for typed config
  read from env / GCP Secret Manager. Validate **every** Claude response against the committed
  JSON Schemas (see `ghostwire-schemas`) — malformed/ungrounded output fails fast.
- **SQLAlchemy 2 async** over **asyncpg** (`postgresql+asyncpg://`); one `AsyncSession` per
  request via a FastAPI dependency; `expire_on_commit=False`. **Alembic** (async `env.py`) for
  migrations — versioned & reviewable (audit NFR).
- **ARQ** (Redis) for off-hot-path work: embedding/re-index, feedback batch analysis, long
  team-scoring — keeps the chatbot's **<2s** SLA.
- **structlog** (JSON) initialized **after OpenTelemetry** so `trace_id`/`span_id` inject into
  every log line. Model the RAG pipeline as explicit spans:
  `retrieve → build_context → claude_call → grounding_check`. This trace-log correlation IS
  the AI-decision audit backbone.

## Claude client (credential-agnostic — IMPORTANT)
One wrapper, used everywhere the app calls Claude. It must work with **either** credential:
- **Console key:** `ANTHROPIC_API_KEY=sk-ant-api…` → standard `Anthropic()` (`x-api-key`).
- **Subscription OAuth (local demo, our `.env`):** `ANTHROPIC_AUTH_TOKEN=sk-ant-oat01…` →
  `Anthropic(auth_token=...)` (sends `Authorization: Bearer`) **plus** the header
  `anthropic-beta: oauth-2025-04-20` (set via `default_headers`). The OAuth path is
  inference-only and draws from the shared subscription window — **smoke-test it early** in
  Phase B (one cheap call) before relying on it; keep eval corpora small.
- Selection: prefer `ANTHROPIC_API_KEY` if set, else `ANTHROPIC_AUTH_TOKEN`, else a clearly
  labelled **stub** client (deterministic canned grounded answer) so local boot/tests pass
  without a credential — but the semantic gate (AC-1/3/4) only counts when a real credential
  is wired.
- Model ids: `claude-opus-4-8` (default), `claude-sonnet-4-6`, `claude-haiku-4-5`. Use
  **adaptive thinking** (`thinking={"type":"adaptive"}`) for non-trivial calls; **stream** for
  large outputs; **prompt-cache** the frozen system prompt + tool list (put stable content
  first, `cache_control` on the last stable block). Always check `stop_reason` before reading
  `content`. (Confirm exact SDK usage via the `claude-api` skill.)

## RAG / grounding
- Retrieve from **Weaviate** (hybrid BM25+dense, alpha-tuned), small `k`; build a
  citation-tagged context; prompt Claude to answer **only** from context with per-claim
  `source_id`s; validate against `rag_answer.schema.json`; run a faithfulness judge and
  **abstain** below threshold (never guess). Eval with **Ragas** (explore) → **DeepEval**
  (CI gate); optional **Langfuse** for live groundedness.

## Frontend (React)
- **Vite** + **TanStack Query** (server state: RAG/feedback fetch, caching, dedup) +
  Router + **Tailwind** + **shadcn/ui**. **TanStack Table** for feedback dashboards & candidate
  grids; **React Hook Form + Zod** for forms and client-side response validation. Use the
  `frontend-design` skill for visual quality. Three surfaces: public chat widget, internal
  feedback dashboard, internal team-assembly UI.

## Quality gates (CI + pre-commit)
- **Ruff** (lint+format), **Pyright** (or mypy), **pytest + pytest-asyncio + httpx.AsyncClient**,
  **testcontainers** (ephemeral Postgres + Weaviate), and a **DeepEval RAG-faithfulness** suite
  as a required gate. Frontend: `tsc`, eslint, vitest. See `verify-loop` for the order.

## Local bring-up & GCP
- **docker-compose**: `postgres`, `weaviate`, `backend` (FastAPI/uvicorn), `frontend` (Vite),
  optional `redis` (ARQ). Health endpoints + a seed script for a tiny corpus. This is the
  Phase-B "working app" target.
- **GCP as Terraform/IaC artifacts only** (not deployed): Cloud Run (2nd gen) + Serverless VPC
  Access + Cloud SQL Auth Proxy; Cloud SQL Postgres (private IP, PITR); Memorystore Redis;
  Secret Manager (Claude credential + DB creds); Artifact Registry; Cloud Trace/Logging (OTel).
