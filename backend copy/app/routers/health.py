"""Liveness/readiness router."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Matches the frozen OpenAPI /health response: {status:"ok", version}."""
    return {"status": "ok", "version": get_settings().app_version}
