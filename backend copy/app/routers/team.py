"""AI Team Assembler router — Module 3 of GHOSTWIRE.

POST /team/assemble
  - RBAC: manager or admin (reads sensitive employee + feedback data — internal only).
  - Analyzes a project description, scores candidates using skill-match AND behavioral
    feedback signals (AC-3 cross-edge: FeedbackIntelligence.get_async), then assembles a
    team with per-member rationale (AC-5 explainability) and feedback_signal_ref pointing
    at the resolvable FeedbackAnalysis.analysis_id.
  - Returns TeamAssembly (system/contracts/schemas/team_assembly.schema.json).
  - Sets X-Trace-Id response header (per openapi.yaml contract).

NOTE for the lead: this router is NOT mounted in app/main.py yet.  Add:
    from app.routers import team
    app.include_router(team.router)
to app/main.py's create_app() to activate it.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.contracts import AuthContext
from app.llm import ClaudeRefusal, ClaudeUnavailable
from app.shared_security import require_auth
from app.team_assembler.service import assemble_team

router = APIRouter(prefix="/team", tags=["team"])


# ---------------------------------------------------------------------------
# Request / response Pydantic models (Pydantic v2 style, mirrors openapi.yaml)
# ---------------------------------------------------------------------------


class ConstraintsIn(BaseModel):
    timeline: str | None = None
    budget: str | None = None
    timezone: str | None = None


class AssembleRequest(BaseModel):
    project_description: str = Field(..., description="Description of the project to staff.")
    requirements: list[str] = Field(
        default_factory=list,
        description="Optional list of specific project requirements.",
    )
    constraints: ConstraintsIn = Field(
        default_factory=ConstraintsIn,
        description="Optional constraints: timeline, budget, timezone.",
    )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/assemble")
async def assemble(
    body: AssembleRequest,
    auth_ctx: Annotated[AuthContext, Depends(require_auth({"manager", "admin"}))],
) -> JSONResponse:
    """Analyze a project and assemble an optimal team from available candidates.

    INTERNAL — requires manager or admin role (reads sensitive employee and feedback data).

    Scoring weights:
      - Skill match (embedding cosine + keyword overlap): 35%
      - Feedback score from FeedbackIntelligence (AC-3 cross-edge):  30%
      - Experience fit (project history count):                       20%
      - Availability:                                                  10%
      - Team compatibility (burnout/conflict risk from feedback):       5%

    Every selected team member includes:
      - feedback_signal_ref.source  = FeedbackAnalysis.analysis_id (resolvable record id)
      - feedback_signal_ref.signal  = human-readable behavioral signal summary
      - rationale                   = per-member explanation (AC-5)

    Returns X-Trace-Id header correlated with the append-only audit row.
    """
    trace_id = str(uuid.uuid4())

    constraints_dict: dict[str, str] = {}
    if body.constraints.timeline:
        constraints_dict["timeline"] = body.constraints.timeline
    if body.constraints.budget:
        constraints_dict["budget"] = body.constraints.budget
    if body.constraints.timezone:
        constraints_dict["timezone"] = body.constraints.timezone

    try:
        result: dict = await assemble_team(
            project_description=body.project_description,
            requirements=body.requirements,
            constraints=constraints_dict,
            auth_ctx=auth_ctx,
            trace_id=trace_id,
        )
    except (ClaudeRefusal, ClaudeUnavailable) as e:
        raise HTTPException(
            status_code=503, detail=f"AI team assembly temporarily unavailable: {e}"
        ) from e

    return JSONResponse(
        content=result,
        headers={"X-Trace-Id": trace_id},
    )
