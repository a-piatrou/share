"""FastAPI app factory + lifespan. Phase-1 mounts only /health.

OTel is initialized before structlog (so trace ids inject into logs). The feature routers
(chat/feedback/team) exist but are intentionally not mounted — that is Phase-2 work owned by the
feature worktrees. The Weaviate client (if opened) is closed on shutdown.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.config import get_settings
from app.observability import init_observability
from app.routers import chat, feedback, health, team


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_observability()
    log = structlog.get_logger()
    log.info("startup", service=get_settings().service_name, version=get_settings().app_version)
    try:
        yield
    finally:
        # Best-effort cleanup of the lazy Weaviate client if it was opened.
        try:
            from app.knowledge_core.weaviate_core import close_weaviate_client

            close_weaviate_client()
        except Exception:  # noqa: BLE001 - shutdown must not raise
            pass
        log.info("shutdown")


def create_app() -> FastAPI:
    # OTel must be set up before the first structlog call.
    init_observability()
    app = FastAPI(
        title="GHOSTWIRE API",
        version=get_settings().app_version,
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(chat.router)  # Module 1 — public RAG chatbot
    app.include_router(feedback.router)  # Module 2 — Feedback Intelligence (RBAC)
    app.include_router(team.router)  # Module 3 — AI Team Assembler (RBAC)
    return app


app = create_app()
