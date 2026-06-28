"""Feedback Intelligence router — Phase-2 implementation (feedback-builder worktree).

POST /feedback/analyze
  - RBAC: manager or admin (internal employee data — never public).
  - Reads reviews, drives the real LLM analysis via app.feedback.service.analyze_reviews.
  - Returns FeedbackAnalysis (schema: system/contracts/schemas/feedback_analysis.schema.json).
  - Sets X-Trace-Id response header (per openapi.yaml contract).
  - Persists the result so team_assembler can read it via FeedbackIntelligence.get_async().

NOTE for the lead: this router is NOT mounted in app/main.py yet.  Add
    from app.routers import feedback
    app.include_router(feedback.router)
to app/main.py's create_app() to activate it.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.contracts import AuthContext, EvidenceRef, FeedbackAnalysis, Review
from app.feedback.service import analyze_reviews
from app.llm import ClaudeRefusal, ClaudeUnavailable
from app.shared_security import require_auth

router = APIRouter(prefix="/feedback", tags=["feedback"])


# ---------------------------------------------------------------------------
# Request / response Pydantic models (Pydantic v2 style).
# The response shape mirrors FeedbackAnalysis + feedback_analysis.schema.json.
# ---------------------------------------------------------------------------


class ReviewIn(BaseModel):
    review_id: str
    kind: Literal["peer", "manager", "self"]
    text: str


class AnalyzeRequest(BaseModel):
    employee_id: str
    reviews: list[ReviewIn]


class EvidenceRefOut(BaseModel):
    review_id: str
    quote: str


class EvidencedItemOut(BaseModel):
    text: str
    evidence_ref: EvidenceRefOut


class RiskOut(BaseModel):
    type: Literal["burnout", "conflict", "attrition", "performance", "other"]
    text: str
    severity: Literal["low", "medium", "high"]
    evidence_ref: EvidenceRefOut


class FeedbackAnalysisOut(BaseModel):
    analysis_id: str
    employee_id: str
    feedback_score: float
    sentiment: float
    strengths: list[EvidencedItemOut]
    weaknesses: list[EvidencedItemOut]
    risks: list[RiskOut]
    team_dynamics_signals: list[EvidencedItemOut]
    confidence_score: float


# ---------------------------------------------------------------------------
# Helpers to convert the FeedbackAnalysis dataclass to the response model.
# FeedbackAnalysis.strengths/weaknesses/team_dynamics_signals are
# list[tuple[str, EvidenceRef]] (frozen contract shape).
# ---------------------------------------------------------------------------


def _ev(ev: EvidenceRef) -> EvidenceRefOut:
    return EvidenceRefOut(review_id=ev.review_id, quote=ev.quote)


def _items(pairs: list[tuple[str, EvidenceRef]]) -> list[EvidencedItemOut]:
    return [EvidencedItemOut(text=text, evidence_ref=_ev(ev)) for text, ev in pairs]


def _risk_out(r: dict) -> RiskOut:
    ev = r.get("evidence_ref", {})
    return RiskOut(
        type=r.get("type", "other"),
        text=r.get("text", ""),
        severity=r.get("severity", "low"),
        evidence_ref=EvidenceRefOut(
            review_id=ev.get("review_id", ""),
            quote=ev.get("quote", ""),
        ),
    )


def _to_response(analysis: FeedbackAnalysis) -> FeedbackAnalysisOut:
    return FeedbackAnalysisOut(
        analysis_id=analysis.analysis_id,
        employee_id=analysis.employee_id,
        feedback_score=analysis.feedback_score,
        sentiment=analysis.sentiment,
        strengths=_items(analysis.strengths),
        weaknesses=_items(analysis.weaknesses),
        risks=[_risk_out(r) for r in analysis.risks],
        team_dynamics_signals=_items(analysis.team_dynamics_signals),
        confidence_score=analysis.confidence_score,
    )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/analyze", response_model=FeedbackAnalysisOut)
async def analyze(
    body: AnalyzeRequest,
    auth_ctx: Annotated[AuthContext, Depends(require_auth({"manager", "admin"}))],
) -> JSONResponse:
    """Analyze a review set and return structured feedback intelligence.

    INTERNAL — requires manager or admin role (reads sensitive employee data).
    Persists the result keyed by employee_id so team_assembler can retrieve it.
    Returns X-Trace-Id header for audit correlation.
    """
    trace_id = str(uuid.uuid4())

    # Build frozen Review dataclass objects from the request payload.
    reviews = [
        Review(
            review_id=r.review_id,
            employee_id=body.employee_id,
            kind=r.kind,
            text=r.text,
        )
        for r in body.reviews
    ]

    try:
        analysis = await analyze_reviews(
            employee_id=body.employee_id,
            reviews=reviews,
            auth_ctx=auth_ctx,
            trace_id=trace_id,
        )
    except (ClaudeRefusal, ClaudeUnavailable) as e:
        raise HTTPException(
            status_code=503, detail=f"AI analysis temporarily unavailable: {e}"
        ) from e

    response_body = _to_response(analysis)
    return JSONResponse(
        content=response_body.model_dump(),
        headers={"X-Trace-Id": trace_id},
    )
