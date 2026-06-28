# GHOSTWIRE backend — shared brain (knowledge_core + shared_security)

The serial critical path: the single Knowledge Core, the shared security/RBAC/audit
library, and the FastAPI app scaffold that the chatbot / feedback / team_assembler
feature modules all depend on.

## Layout
- `app/contracts.py` — re-exports the FROZEN types from
  `system/contracts/stubs/shared_interfaces.py` (single source of truth; no drift).
- `app/config.py` — typed settings (pydantic-settings).
- `app/db/` — async SQLAlchemy engine + session dependency + ORM models + Alembic.
- `app/shared_security/` — `build_auth_context`, `require_auth`, `AuditSink`.
- `app/knowledge_core/` — `EmbeddingService`, `KnowledgeCore` (Weaviate multi-tenant),
  `EmployeeRepository`, `FeedbackIntelligence`, ingestion.
- `app/main.py` — FastAPI app factory + `/health` + OTel/structlog wiring.

## Bring-up
See the repo root `Makefile` and `docker-compose.yml`. In short:

```bash
# from repo root
docker compose up -d                      # postgres, weaviate, t2v-transformers
cd backend
python3 -m uv venv --python 3.12 .venv
python3 -m uv pip install -e ".[dev]"
make verify                               # tier-1 deterministic gate
.venv/bin/alembic upgrade head            # create tables (needs postgres)
.venv/bin/python -m app.knowledge_core.ingest   # seed Postgres + Weaviate
.venv/bin/uvicorn app.main:app --reload   # http://localhost:8000/health
```

Copy `.env.example` to `.env` and fill in as needed (`.env` is gitignored — never commit secrets).
