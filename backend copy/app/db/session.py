"""Async SQLAlchemy engine + one-AsyncSession-per-request dependency.

``expire_on_commit=False`` so attribute access after commit does not trigger lazy reloads
(important under async — avoids implicit IO outside the request scope). The session is opened
and closed per request via the FastAPI dependency ``get_session``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields one AsyncSession per request and always closes it."""
    async with async_session_factory() as session:
        yield session
