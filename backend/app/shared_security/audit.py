"""Append-only AI-decision audit sink (the audit NFR backbone).

``AuditSink.append(row)`` is the only write path; there is no update/delete method anywhere.
The Postgres role used by the app also has UPDATE/DELETE on ``audit_rows`` revoked at the DDL
level (see the audit-grants Alembic migration), so append-only holds below the application too.

The sink runs its own short-lived AsyncSession per append so it is callable from anywhere
(request handlers, background tasks, the ingestion script) without threading a session through.
``append`` is sync in the frozen Protocol; we expose that plus an ``append_async`` coroutine for
callers already inside an event loop.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache

from app.contracts import AuditRow
from app.db.models import AuditRowORM
from app.db.session import async_session_factory


class PostgresAuditSink:
    """Concrete append-only AuditSink backed by Postgres (satisfies the AuditSink Protocol)."""

    async def append_async(self, row: AuditRow) -> None:
        async with async_session_factory() as session:
            session.add(
                AuditRowORM(
                    trace_id=row.trace_id,
                    timestamp=row.timestamp,
                    principal_id=row.principal_id,
                    module=row.module,
                    inputs_hash=row.inputs_hash,
                    retrieved_chunk_ids=list(row.retrieved_chunk_ids),
                    prompt_version=row.prompt_version,
                    model_version=row.model_version,
                    output_ref=row.output_ref,
                    grounding_score=row.grounding_score,
                    tenant=row.tenant,
                )
            )
            await session.commit()

    def append(self, row: AuditRow) -> None:
        """Synchronous Protocol method. Schedules the async append.

        If called from within a running event loop, the coroutine is scheduled as a task
        (fire-and-forget audit write); otherwise it is run to completion. Callers already in
        async code should prefer ``append_async`` and await it.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.append_async(row))
            return
        loop.create_task(self.append_async(row))


@lru_cache
def get_audit_sink() -> PostgresAuditSink:
    """The single shared AuditSink accessor (AC-4 discipline)."""
    return PostgresAuditSink()
