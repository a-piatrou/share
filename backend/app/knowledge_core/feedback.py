"""FeedbackIntelligence persistence + get() path (the team_assembler cross-edge).

Phase-1 scope: the persistence + ``get()`` path must work so team_assembler can consume
``FeedbackAnalysis`` records. The full LLM-based, evidence-grounded analysis is the feedback
module's Phase-2 job; here ``analyze()`` is a THIN DETERMINISTIC stub that:
  - extracts strength/weakness/risk items with a verbatim EvidenceRef quote drawn from a real
    input review (so every item is evidence-bearing — the AC-2 shape, proven for real in Phase 2),
  - computes ``feedback_score`` with the FROZEN deterministic formula
    (glossary.feedback_score_formula: start 0.5; +0.08/strength, -0.06/weakness,
    -{low:0.05,medium:0.10,high:0.20}/risk; clamp [0,1]) so the AC-3 corpus-mutation test moves it,
  - persists the result keyed by employee_id, and
  - ``get(employee_id)`` returns the latest persisted analysis.

RBAC: feedback is internal data. A principal needs the ``feedback`` domain AND the matching
``internal:<org>`` tenant (manager/admin in the demo policy). Otherwise analyze/get refuse.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import select

from app.contracts import (
    AuthContext,
    EvidenceRef,
    FeedbackAnalysis,
    Review,
)
from app.db.models import FeedbackAnalysisRowORM
from app.db.session import async_session_factory

_RISK_PENALTY = {"low": 0.05, "medium": 0.10, "high": 0.20}

# Lowercased keyword cues for the deterministic stub. Phase-2 replaces this with an LLM judge.
_STRENGTH_CUES = (
    "strong",
    "excellent",
    "outstanding",
    "best",
    "reliable",
    "rigorous",
    "mentor",
    "trusted",
    "force-multiplier",
    "high-quality",
    "pleasure",
    "brilliant",
    "solid",
    "role model",
)
_WEAKNESS_CUES = (
    "reluctant",
    "bottleneck",
    "too much",
    "stretched",
    "slow",
    "missed",
    "dipped",
    "slipped",
    "rework",
    "inconsistency",
    "single point of failure",
    "scope creep",
)
_RISK_CUES = {
    "burnout": (
        ("burnout", "high"),
        ("running on empty", "high"),
        ("exhausted", "medium"),
        ("long hours", "medium"),
        ("on call", "low"),
    ),
    "conflict": (
        ("conflict", "high"),
        ("clashed", "medium"),
        ("friction", "medium"),
        ("tense", "medium"),
    ),
    "attrition": (
        ("right role for me", "high"),
        ("disengaged", "medium"),
        ("wondering whether", "medium"),
    ),
    "performance": (
        ("deadlines slipped", "medium"),
        ("quality issues", "medium"),
        ("performance has dipped", "medium"),
    ),
}


def _can_access_feedback(auth_ctx: AuthContext, org: str = "godeltech") -> bool:
    return "feedback" in auth_ctx.allowed_domains and f"internal:{org}" in auth_ctx.allowed_tenants


def _first_sentence_containing(text: str, needle: str) -> str:
    """Return a verbatim sentence-ish snippet from text containing needle (the evidence quote)."""
    low = text.lower()
    idx = low.find(needle)
    if idx == -1:
        return text.strip()[:160]
    # expand to sentence boundaries around the hit
    start = text.rfind(".", 0, idx)
    start = 0 if start == -1 else start + 1
    end = text.find(".", idx)
    end = len(text) if end == -1 else end + 1
    return text[start:end].strip()


def _evidence(reviews: list[Review], needle: str) -> tuple[Review, str] | None:
    for r in reviews:
        if needle in r.text.lower():
            return r, _first_sentence_containing(r.text, needle)
    return None


def _analyze_deterministic(employee_id: str, reviews: list[Review]) -> FeedbackAnalysis:
    strengths: list[tuple[str, EvidenceRef]] = []
    weaknesses: list[tuple[str, EvidenceRef]] = []
    risks: list[dict] = []
    seen_quotes: set[str] = set()

    def add_item(bucket: list, label: str, cue: str) -> bool:
        hit = _evidence(reviews, cue)
        if not hit:
            return False
        review, quote = hit
        if quote in seen_quotes:
            return False
        seen_quotes.add(quote)
        bucket.append((label, EvidenceRef(review_id=review.review_id, quote=quote)))
        return True

    for cue in _STRENGTH_CUES:
        add_item(strengths, f"Demonstrates {cue}", cue)
    for cue in _WEAKNESS_CUES:
        add_item(weaknesses, f"Concern: {cue}", cue)

    for risk_type, cues in _RISK_CUES.items():
        for cue, severity in cues:
            hit = _evidence(reviews, cue)
            if hit and hit[1] not in seen_quotes:
                review, quote = hit
                seen_quotes.add(quote)
                risks.append(
                    {
                        "type": risk_type,
                        "text": f"Possible {risk_type} signal ('{cue}')",
                        "severity": severity,
                        "evidence_ref": {"review_id": review.review_id, "quote": quote},
                    }
                )
                break  # one (highest-priority) evidence per risk type

    # Deterministic feedback_score (frozen formula).
    score = 0.5 + 0.08 * len(strengths) - 0.06 * len(weaknesses)
    for r in risks:
        score -= _RISK_PENALTY.get(r["severity"], 0.0)
    feedback_score = max(0.0, min(1.0, score))

    # Sentiment: simple normalized strength-vs-weakness balance in [-1,1].
    total = len(strengths) + len(weaknesses) + len(risks)
    sentiment = 0.0 if total == 0 else (len(strengths) - len(weaknesses) - len(risks)) / total
    sentiment = max(-1.0, min(1.0, sentiment))

    # Confidence in THIS analysis: more reviews -> more confident (capped).
    confidence_score = max(0.0, min(1.0, 0.4 + 0.2 * len(reviews)))

    # team_dynamics_signals: reuse conflict/collaboration evidence as a coarse signal.
    team_signals: list[tuple[str, EvidenceRef]] = []
    for cue, label in (
        ("collaborat", "Collaborative"),
        ("facilitat", "Strong facilitator"),
        ("friction", "Team friction"),
        ("clashed", "Interpersonal clash"),
    ):
        hit = _evidence(reviews, cue)
        if hit:
            review, quote = hit
            team_signals.append((label, EvidenceRef(review_id=review.review_id, quote=quote)))

    analysis_id = (
        "FA-"
        + hashlib.sha1(
            (employee_id + "|" + "|".join(sorted(r.review_id for r in reviews))).encode()
        ).hexdigest()[:16]
    )

    return FeedbackAnalysis(
        analysis_id=analysis_id,
        employee_id=employee_id,
        feedback_score=feedback_score,
        sentiment=sentiment,
        strengths=strengths,
        weaknesses=weaknesses,
        risks=risks,
        team_dynamics_signals=team_signals,
        confidence_score=confidence_score,
    )


def _serialize_items(items: list[tuple[str, EvidenceRef]]) -> list[dict]:
    return [
        {"text": text, "evidence_ref": {"review_id": ev.review_id, "quote": ev.quote}}
        for text, ev in items
    ]


def _deserialize_items(rows: list[dict]) -> list[tuple[str, EvidenceRef]]:
    out: list[tuple[str, EvidenceRef]] = []
    for it in rows or []:
        ev = it.get("evidence_ref", {})
        out.append(
            (
                it.get("text", ""),
                EvidenceRef(review_id=ev.get("review_id", ""), quote=ev.get("quote", "")),
            )
        )
    return out


def _row_to_analysis(row: FeedbackAnalysisRowORM) -> FeedbackAnalysis:
    return FeedbackAnalysis(
        analysis_id=row.analysis_id,
        employee_id=row.employee_id,
        feedback_score=row.feedback_score,
        sentiment=row.sentiment,
        strengths=_deserialize_items(row.strengths),
        weaknesses=_deserialize_items(row.weaknesses),
        risks=list(row.risks or []),
        team_dynamics_signals=_deserialize_items(row.team_dynamics_signals),
        confidence_score=row.confidence_score,
    )


class FeedbackIntelligenceImpl:
    """Concrete FeedbackIntelligence (satisfies the Protocol). Persists + reads FeedbackAnalysis."""

    async def analyze_async(
        self, reviews: list[Review], auth_ctx: AuthContext, org: str = "godeltech"
    ) -> FeedbackAnalysis:
        if not _can_access_feedback(auth_ctx, org):
            raise PermissionError("principal not authorized for feedback domain/tenant")
        if not reviews:
            raise ValueError("analyze() requires at least one review")
        employee_id = reviews[0].employee_id
        analysis = _analyze_deterministic(employee_id, reviews)
        await self._persist(analysis, org)
        return analysis

    async def _persist(self, analysis: FeedbackAnalysis, org: str) -> None:
        async with async_session_factory() as session:
            existing = await session.get(FeedbackAnalysisRowORM, analysis.analysis_id)
            if existing is None:
                session.add(
                    FeedbackAnalysisRowORM(
                        analysis_id=analysis.analysis_id,
                        employee_id=analysis.employee_id,
                        org=org,
                        created_at=datetime.now(UTC),
                        feedback_score=analysis.feedback_score,
                        sentiment=analysis.sentiment,
                        confidence_score=analysis.confidence_score,
                        strengths=_serialize_items(analysis.strengths),
                        weaknesses=_serialize_items(analysis.weaknesses),
                        risks=list(analysis.risks),
                        team_dynamics_signals=_serialize_items(analysis.team_dynamics_signals),
                    )
                )
                await session.commit()

    async def get_async(
        self, employee_id: str, auth_ctx: AuthContext, org: str = "godeltech"
    ) -> FeedbackAnalysis | None:
        if not _can_access_feedback(auth_ctx, org):
            return None
        async with async_session_factory() as session:
            row = (
                await session.execute(
                    select(FeedbackAnalysisRowORM)
                    .where(FeedbackAnalysisRowORM.employee_id == employee_id)
                    .order_by(FeedbackAnalysisRowORM.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            return _row_to_analysis(row) if row is not None else None

    # --- sync Protocol surface ---

    def analyze(self, reviews: list[Review], auth_ctx: AuthContext) -> FeedbackAnalysis:
        return _run_sync(self.analyze_async(reviews, auth_ctx))

    def get(self, employee_id: str, auth_ctx: AuthContext) -> FeedbackAnalysis | None:
        return _run_sync(self.get_async(employee_id, auth_ctx))


def _run_sync(coro):
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError(
        "FeedbackIntelligence sync method called from within an event loop; "
        "await the *_async variant instead."
    )


_fi: FeedbackIntelligenceImpl | None = None


def get_feedback_intelligence() -> FeedbackIntelligenceImpl:
    """The single shared FeedbackIntelligence accessor (AC-4 discipline)."""
    global _fi
    if _fi is None:
        _fi = FeedbackIntelligenceImpl()
    return _fi
