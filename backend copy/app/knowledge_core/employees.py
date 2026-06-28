"""EmployeeRepository — structured employee profiles from Postgres (internal, RBAC-scoped).

team_assembler enumerates candidates and reads profiles through THIS (not opaque chunks). It is
internal data: a principal must have the ``employee_profiles`` domain AND the matching
``internal:<org>`` tenant in its AuthContext, or get nothing back (the public context gets []).
``feedback_summary`` is filled from the persisted FeedbackIntelligence record when present, so
the unified EmployeeIntelligenceProfile (REQ-002) reflects feedback without re-running analysis.
"""

from __future__ import annotations

import re

from sqlalchemy import select

from app.contracts import AuthContext, EmployeeIntelligenceProfile
from app.db.models import EmployeeORM, FeedbackAnalysisRowORM
from app.db.session import async_session_factory

# Generic joiner words that must not create spurious skill overlaps in the coarse pre-filter.
_SKILL_STOPWORDS = frozenset(
    {"and", "or", "the", "of", "for", "with", "a", "an", "to", "in", "on", "using"}
)


def _skill_tokens(skills: list[str]) -> set[str]:
    """Lowercased alphanumeric tokens across skill strings, for LENIENT overlap matching.

    The candidate pre-filter is a coarse gate; the real ranking is embedding-based in scoring.py.
    LLM-extracted requirements ('Python/FastAPI', 'GCP Cloud Run', 'Vector DB (Weaviate)') must be
    able to match single-token seed skills ('Python', 'FastAPI', 'GCP', 'Weaviate'); exact-string
    set intersection is too brittle for that and silently empties the candidate pool. We keep '+'
    and '#' so 'c++'/'c#' survive tokenisation.
    """
    tokens: set[str] = set()
    for s in skills:
        for tok in re.split(r"[^a-z0-9+#]+", s.lower()):
            if len(tok) >= 2 and tok not in _SKILL_STOPWORDS:
                tokens.add(tok)
    return tokens


def _can_read_internal(auth_ctx: AuthContext, org: str) -> bool:
    return (
        "employee_profiles" in auth_ctx.allowed_domains
        and f"internal:{org}" in auth_ctx.allowed_tenants
    )


def _to_profile(row: EmployeeORM, feedback_summary: str | None) -> EmployeeIntelligenceProfile:
    return EmployeeIntelligenceProfile(
        employee_id=row.employee_id,
        name=row.name,
        cv_text=row.cv_text,
        skills=list(row.skills or []),
        feedback_summary=feedback_summary,
        project_history=list(row.project_history or []),
        availability=row.availability,
    )


class EmployeeRepositoryImpl:
    """Concrete EmployeeRepository (satisfies the EmployeeRepository Protocol).

    The frozen Protocol methods are sync; under async they delegate to async helpers. Callers
    already in an event loop should use ``get_async`` / ``list_candidates_async``.
    """

    async def _feedback_summary(self, session, employee_id: str) -> str | None:
        latest = (
            await session.execute(
                select(FeedbackAnalysisRowORM)
                .where(FeedbackAnalysisRowORM.employee_id == employee_id)
                .order_by(FeedbackAnalysisRowORM.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest is None:
            return None
        strengths = [s.get("text") for s in (latest.strengths or []) if s.get("text")]
        summary = f"feedback_score={latest.feedback_score:.2f}, sentiment={latest.sentiment:.2f}"
        if strengths:
            summary += "; strengths: " + ", ".join(strengths[:3])
        return summary

    async def get_async(
        self, employee_id: str, auth_ctx: AuthContext
    ) -> EmployeeIntelligenceProfile | None:
        async with async_session_factory() as session:
            row = (
                await session.execute(
                    select(EmployeeORM).where(EmployeeORM.employee_id == employee_id)
                )
            ).scalar_one_or_none()
            if row is None or not _can_read_internal(auth_ctx, row.org):
                return None
            summary = await self._feedback_summary(session, row.employee_id)
            return _to_profile(row, summary)

    async def list_candidates_async(
        self, auth_ctx: AuthContext, required_skills: list[str] | None = None
    ) -> list[EmployeeIntelligenceProfile]:
        async with async_session_factory() as session:
            rows = (
                (await session.execute(select(EmployeeORM).order_by(EmployeeORM.employee_id)))
                .scalars()
                .all()
            )
            out: list[EmployeeIntelligenceProfile] = []
            req_tokens = _skill_tokens(required_skills or [])
            for row in rows:
                if not _can_read_internal(auth_ctx, row.org):
                    continue
                if req_tokens:
                    have_tokens = _skill_tokens(list(row.skills or []))
                    if not (req_tokens & have_tokens):
                        continue
                summary = await self._feedback_summary(session, row.employee_id)
                out.append(_to_profile(row, summary))
            return out

    # --- sync Protocol surface (delegates to the async helpers) ---

    def get(self, employee_id: str, auth_ctx: AuthContext) -> EmployeeIntelligenceProfile | None:
        return _run_sync(self.get_async(employee_id, auth_ctx))

    def list_candidates(
        self, auth_ctx: AuthContext, required_skills: list[str] | None = None
    ) -> list[EmployeeIntelligenceProfile]:
        return _run_sync(self.list_candidates_async(auth_ctx, required_skills))


def _run_sync(coro):
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError(
        "EmployeeRepository sync method called from within an event loop; "
        "await the *_async variant instead."
    )


_repo: EmployeeRepositoryImpl | None = None


def get_employee_repository() -> EmployeeRepositoryImpl:
    """The single shared EmployeeRepository accessor (AC-4 discipline)."""
    global _repo
    if _repo is None:
        _repo = EmployeeRepositoryImpl()
    return _repo
