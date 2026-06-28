"""AI Team Assembler service — core pipeline (REQ-008, REQ-009, AC-3, AC-5).

Pipeline:
  1. PROJECT ANALYSIS  — Claude (SONNET) extracts required skills, roles, risk factors.
  2. CANDIDATE LOADING — EmployeeRepository.list_candidates_async (RBAC-scoped).
  3. FEEDBACK FETCH    — FeedbackIntelligence.get_async per candidate (THE cross-edge).
  4. EMBEDDING         — EmbeddingService.embed via run_in_threadpool (sync, GDPR in-VPC).
  5. SCORING           — Composite match_score (see scoring.py for exact weights).
  6. ASSEMBLY          — Top-N per role; schema-valid TeamAssembly with feedback_signal_ref.
  7. RATIONALE (LLM)   — Claude explains the overall selection (AC-5 explainability).
  8. AUDIT             — AuditSink.append_async (append-only, trace_id).

Stub mode (is_real()==False): all steps run with stub data so import + boot pass cleanly.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from starlette.concurrency import run_in_threadpool

from app.contracts import (
    AuditRow,
    AuthContext,
    EmployeeIntelligenceProfile,
    FeedbackAnalysis,
)
from app.knowledge_core import (
    get_embedding_service,
    get_employee_repository,
    get_feedback_intelligence,
)
from app.llm import SONNET, get_claude_client
from app.shared_security import get_audit_sink
from app.team_assembler.scoring import ScoredCandidate, score_candidate

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# JSON Schema paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]
_TEAM_SCHEMA_PATH = _REPO_ROOT / "system" / "contracts" / "schemas" / "team_assembly.schema.json"
_TEAM_SCHEMA: dict[str, Any] = json.loads(_TEAM_SCHEMA_PATH.read_text())

# ---------------------------------------------------------------------------
# Project analysis schema (for structured LLM output)
# ---------------------------------------------------------------------------
_PROJECT_ANALYSIS_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["required_skills", "seniority_levels", "team_roles", "risk_factors"],
    "properties": {
        "required_skills": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Technical and soft skills needed for the project.",
        },
        "seniority_levels": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Seniority mix needed (e.g. senior, mid, junior).",
        },
        "team_roles": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Concrete roles to fill (e.g. Lead Engineer, Backend Dev).",
        },
        "risk_factors": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Project delivery risks to consider during team selection.",
        },
    },
}

_PROJECT_ANALYSIS_SYSTEM = """\
You are an expert technical project manager. Given a project description, extract:
1. required_skills: technical and soft skills the team must cover (be specific, 5-12 skills).
2. seniority_levels: the experience mix needed.
3. team_roles: concrete roles to fill (e.g. "Tech Lead", "Backend Engineer", "QA Engineer").
4. risk_factors: delivery risks that should influence team selection.

Respond ONLY with a JSON object matching the provided schema. Be concise and precise.\
"""


def _project_analysis_user(
    project_description: str,
    requirements: list[str],
    constraints: dict[str, str],
) -> str:
    parts = [f"Project description:\n{project_description}"]
    if requirements:
        parts.append("Requirements:\n" + "\n".join(f"- {r}" for r in requirements))
    if constraints:
        cstr = ", ".join(f"{k}={v}" for k, v in constraints.items())
        parts.append(f"Constraints: {cstr}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Assembly result dataclass (internal; converted to response dict at the router)
# ---------------------------------------------------------------------------


@dataclass
class AssemblyResult:
    team: list[dict]
    gaps: list[dict]
    risks: list[dict]
    alternatives: list[dict]
    rationale: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _feedback_signal_text(scored: ScoredCandidate) -> str:
    """Human-readable feedback signal summary (the 'signal' field of feedback_signal_ref)."""
    fa = scored.analysis
    if fa is None:
        return "no feedback analysis available"

    parts = [f"feedback_score={fa.feedback_score:.2f}"]

    # Burnout / conflict risk summary.
    high_risks = [r for r in fa.risks if r.get("severity") == "high"]
    med_risks = [r for r in fa.risks if r.get("severity") == "medium"]
    if high_risks:
        risk_types = ", ".join(r.get("type", "?") for r in high_risks)
        parts.append(f"high-severity risks: {risk_types}")
    elif med_risks:
        risk_types = ", ".join(r.get("type", "?") for r in med_risks)
        parts.append(f"medium risks: {risk_types}")
    else:
        parts.append("low burnout/conflict risk")

    # Strengths summary (top 2).
    strength_labels = [t for t, _ in fa.strengths[:2]]
    if strength_labels:
        parts.append("strengths: " + "; ".join(strength_labels))

    return "; ".join(parts)


def _member_rationale(
    scored: ScoredCandidate,
    role: str,
    required_skills: list[str],
) -> str:
    """Per-member rationale for AC-5 explainability."""
    p = scored.profile
    matched = [s for s in p.skills if s.lower() in {r.lower() for r in required_skills}]
    lines = [
        f"Selected as {role} with match_score={scored.match_score:.2f}.",
        f"Skill match (weight 35%): {scored.skill_score:.2f}; "
        f"matched skills: {', '.join(matched) if matched else 'none directly matched'}.",
        f"Feedback score (weight 30%): {scored.feedback_score:.2f} "
        f"(from FeedbackIntelligence analysis_id="
        f"{scored.analysis.analysis_id if scored.analysis else 'N/A'}).",
        f"Experience fit (weight 20%): {scored.experience_score:.2f} "
        f"({len(p.project_history)} project(s) in history).",
        f"Availability (weight 10%): {scored.availability_score:.2f} "
        f"(reported: {p.availability or 'unknown'}).",
        f"Team compatibility (weight 5%): {scored.compat_score:.2f}.",
    ]
    if scored.analysis is None:
        lines.append(
            "Note: No feedback analysis found; feedback_score defaulted to 0.0, "
            "increasing selection risk."
        )
    return " ".join(lines)


def _stub_assembly(
    project_description: str,
    auth_ctx: AuthContext,
) -> AssemblyResult:
    """Schema-valid stub output for no-credential / is_real()==False boot path."""
    return AssemblyResult(
        team=[],
        gaps=[{"skill": "Python", "severity": "medium"}],
        risks=[
            {
                "text": "[STUB] No Claude credential configured; real assembly not performed.",
                "severity": "low",
            }
        ],
        alternatives=[],
        rationale=(
            "[STUB] Team assembler running in stub mode (no Claude credential). "
            f"Project: {project_description[:80]}. "
            f"Principal: {auth_ctx.principal_id}."
        ),
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


async def assemble_team(
    *,
    project_description: str,
    requirements: list[str],
    constraints: dict[str, str],
    auth_ctx: AuthContext,
    trace_id: str,
    org: str = "godeltech",
) -> dict:
    """Full team-assembly pipeline.  Returns a dict matching team_assembly.schema.json.

    AC-3: every selected member's match_score is materially influenced by feedback_score
    (weight 0.30) fetched from FeedbackIntelligence.get_async(), and feedback_signal_ref.source
    is set to the resolvable FeedbackAnalysis.analysis_id from that call.

    AC-5: every member carries a rationale, and the overall assembly has a rationale.
    """
    client = get_claude_client()
    # Sonnet for reasoning quality; thinking OFF to keep assembly responsive. The AC-4 guarantee
    # (behavioral data influences selection) lives in the deterministic scorer, not the LLM, so
    # thinking would add latency without moving the acceptance criteria.
    model_version = SONNET

    # ------------------------------------------------------------------
    # 1. PROJECT ANALYSIS
    # ------------------------------------------------------------------
    if client.is_real():
        project_data: dict = client.complete_json(
            system=_PROJECT_ANALYSIS_SYSTEM,
            user=_project_analysis_user(project_description, requirements, constraints),
            schema=_PROJECT_ANALYSIS_SCHEMA,
            model=model_version,
            thinking=False,
        )
    else:
        # Stub: minimal schema-valid project analysis.
        project_data = {
            "required_skills": ["Python", "FastAPI", "PostgreSQL"],
            "seniority_levels": ["senior", "mid"],
            "team_roles": ["Lead Engineer", "Backend Engineer"],
            "risk_factors": ["tight timeline", "missing behavioral data"],
        }

    required_skills: list[str] = project_data.get("required_skills", [])
    team_roles: list[str] = project_data.get("team_roles", [])
    project_risks: list[str] = project_data.get("risk_factors", [])

    log.info(
        "team_assembler.project_analysis",
        trace_id=trace_id,
        required_skills=required_skills,
        team_roles=team_roles,
    )

    # ------------------------------------------------------------------
    # 2. CANDIDATE LOADING (RBAC-scoped via auth_ctx)
    # ------------------------------------------------------------------
    repo = get_employee_repository()
    candidates: list[EmployeeIntelligenceProfile] = await repo.list_candidates_async(
        auth_ctx, required_skills if required_skills else None
    )

    if not candidates:
        log.warning("team_assembler.no_candidates", trace_id=trace_id)

    # ------------------------------------------------------------------
    # 3. FEEDBACK FETCH (the AC-3 cross-edge)
    # ------------------------------------------------------------------
    fi = get_feedback_intelligence()
    analyses: dict[str, FeedbackAnalysis | None] = {}
    for candidate in candidates:
        try:
            fa = await fi.get_async(candidate.employee_id, auth_ctx)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "team_assembler.feedback_fetch_error",
                employee_id=candidate.employee_id,
                error=str(exc),
            )
            fa = None
        analyses[candidate.employee_id] = fa

    # ------------------------------------------------------------------
    # 4. EMBEDDING (sync via run_in_threadpool; GDPR in-VPC model)
    # ------------------------------------------------------------------
    embed_svc = get_embedding_service()

    # Build required-skill embedding (concatenated skill string).
    required_skills_text = (
        " ".join(required_skills) if required_skills else "general software engineering"
    )
    candidate_skill_texts = [
        " ".join(c.skills) if c.skills else "no skills listed" for c in candidates
    ]

    # Embed all in one batch call (run_in_threadpool because embed() is sync).
    all_texts = [required_skills_text] + candidate_skill_texts
    try:
        all_vecs: list[list[float]] = await run_in_threadpool(embed_svc.embed, all_texts)
        required_skill_vec: list[float] = all_vecs[0]
        candidate_vecs: dict[str, list[float]] = {
            c.employee_id: all_vecs[i + 1] for i, c in enumerate(candidates)
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("team_assembler.embed_error", error=str(exc))
        # Fall back to zero vectors — scoring still works (skill component = 0.0).
        required_skill_vec = []
        candidate_vecs = {c.employee_id: [] for c in candidates}

    # ------------------------------------------------------------------
    # 5. CANDIDATE SCORING
    # ------------------------------------------------------------------
    scored: list[ScoredCandidate] = []
    for candidate in candidates:
        sc = score_candidate(
            profile=candidate,
            analysis=analyses[candidate.employee_id],
            candidate_skill_vec=candidate_vecs.get(candidate.employee_id, []),
            required_skill_vec=required_skill_vec,
            required_skills=required_skills,
        )
        scored.append(sc)

    # Sort descending by match_score.
    scored.sort(key=lambda s: s.match_score, reverse=True)

    log.info(
        "team_assembler.scored",
        trace_id=trace_id,
        n_candidates=len(scored),
        top_scores=[round(s.match_score, 3) for s in scored[:5]],
    )

    # ------------------------------------------------------------------
    # 6. ASSEMBLY — top candidate per role; rest become alternatives
    # ------------------------------------------------------------------
    selected_ids: set[str] = set()
    team_members: list[dict] = []
    alternative_members: list[dict] = []

    # For each role, pick the best unselected candidate with a feedback analysis.
    # If none available with feedback, fall through to candidates without feedback
    # (explicitly marked with a risk note per spec rule 5).
    for role in team_roles:
        # Prefer candidates with feedback analysis (AC-3 structural requirement).
        pick: ScoredCandidate | None = None
        for sc in scored:
            if sc.profile.employee_id not in selected_ids:
                if sc.analysis is not None:
                    pick = sc
                    break

        # If no candidate with feedback is left, allow one without (with explicit risk).
        if pick is None:
            for sc in scored:
                if sc.profile.employee_id not in selected_ids:
                    pick = sc
                    break

        if pick is None:
            break  # Exhausted candidates.

        selected_ids.add(pick.profile.employee_id)

        # Build feedback_signal_ref (AC-3 structural).
        if pick.analysis is not None:
            signal_ref = {
                "source": pick.analysis.analysis_id,  # resolvable FeedbackAnalysis record id
                "signal": _feedback_signal_text(pick),
            }
        else:
            # No feedback analysis exists: document explicitly (spec rule 5).
            # We include the candidate but flag the gap clearly.
            signal_ref = {
                "source": "MISSING",
                "signal": "No FeedbackIntelligence record found; behavioral data unavailable. "
                "This candidate carries elevated selection risk.",
            }

        team_members.append(
            {
                "employee_id": pick.profile.employee_id,
                "role": role,
                "match_score": round(pick.match_score, 4),
                "feedback_signal_ref": signal_ref,
                "rationale": _member_rationale(pick, role, required_skills),
            }
        )

    # Alternatives: next best scored candidates not selected, top 3.
    for sc in scored:
        if sc.profile.employee_id not in selected_ids and len(alternative_members) < 3:
            alternative_members.append(
                {
                    "employee_id": sc.profile.employee_id,
                    "role": team_roles[len(alternative_members) % max(len(team_roles), 1)],
                    "match_score": round(sc.match_score, 4),
                }
            )

    # ------------------------------------------------------------------
    # 7. GAPS ANALYSIS
    # ------------------------------------------------------------------
    covered_skills: set[str] = set()
    for member in team_members:
        eid = member["employee_id"]
        for sc in scored:
            if sc.profile.employee_id == eid:
                covered_skills.update(s.lower() for s in sc.profile.skills)
                break

    gaps: list[dict] = []
    for skill in required_skills:
        if skill.lower() not in covered_skills:
            gaps.append({"skill": skill, "severity": "medium"})

    # Flag missing behavioral data as a gap.
    missing_fb_count = len(
        [s for s in scored if s.analysis is None and s.profile.employee_id in selected_ids]
    )
    if missing_fb_count > 0:
        gaps.append(
            {
                "skill": "Behavioral/Feedback Data",
                "severity": "high" if missing_fb_count > 1 else "medium",
            }
        )

    # ------------------------------------------------------------------
    # 8. RISKS ASSEMBLY
    # ------------------------------------------------------------------
    assembly_risks: list[dict] = []
    for risk_text in project_risks:
        assembly_risks.append({"text": risk_text, "severity": "medium"})

    # Propagate high-severity individual feedback risks to the team level.
    for sc in scored:
        if sc.profile.employee_id in selected_ids and sc.analysis:
            for r in sc.analysis.risks:
                if r.get("severity") == "high":
                    assembly_risks.append(
                        {
                            "text": (
                                f"{sc.profile.name}: {r.get('text', 'Unknown risk')} "
                                f"(type={r.get('type', 'other')})"
                            ),
                            "severity": "high",
                        }
                    )

    # No candidates with feedback at all is a systemic risk.
    if not any(analyses.values()):
        assembly_risks.append(
            {
                "text": (
                    "No FeedbackIntelligence records found for any candidate. "
                    "Team selection based on skills and experience only; "
                    "behavioral risk is unquantified."
                ),
                "severity": "high",
            }
        )

    # ------------------------------------------------------------------
    # 9. OVERALL RATIONALE (LLM) — AC-5 explainability
    # ------------------------------------------------------------------
    if client.is_real() and team_members:
        rationale_prompt = (
            f"You assembled a team for this project:\n{project_description}\n\n"
            f"Selected team members:\n"
            + "\n".join(
                f"- {m['employee_id']} as {m['role']} (match_score={m['match_score']:.2f}): "
                f"{m['rationale']}"
                for m in team_members
            )
            + f"\n\nProject risks identified: {', '.join(project_risks)}."
            "\n\nWrite a concise (2-4 sentences) overall team composition rationale "
            "explaining why this team is well-suited for the project, referencing "
            "skill coverage, behavioral signals, and any gaps or risks. "
            "Do NOT fabricate specific review details."
        )
        rationale = client.complete_text(
            system=(
                "You are an expert technical project manager writing an AI-generated "
                "team selection rationale. Be concise, factual, and reference the "
                "specific scores and signals provided."
            ),
            user=rationale_prompt,
            model=model_version,
            thinking=False,  # latency: off for this short output
            max_tokens=512,
        )
    elif team_members:
        fb_count = sum(1 for m in team_members if m["feedback_signal_ref"]["source"] != "MISSING")
        rationale = (
            f"Team assembled for: {project_description[:120]}. "
            f"Selected {len(team_members)} member(s) covering roles: "
            f"{', '.join(m['role'] for m in team_members)}. "
            f"Feedback intelligence integrated for {fb_count} of {len(team_members)} member(s). "
            f"Gaps: {', '.join(g['skill'] for g in gaps) if gaps else 'none'}. "
            f"Risks: {len(assembly_risks)} identified."
        )
    else:
        rationale = (
            f"No candidates could be assembled for: {project_description[:120]}. "
            "This may be due to RBAC restrictions or an empty candidate pool. "
            "Review team skill coverage and ensure feedback analyses are available."
        )

    # ------------------------------------------------------------------
    # 10. BUILD final result dict
    # ------------------------------------------------------------------
    result = {
        "team": team_members,
        "gaps": gaps,
        "risks": assembly_risks,
        "alternatives": alternative_members,
        "rationale": rationale,
    }

    # ------------------------------------------------------------------
    # 11. AUDIT (append-only AuditSink)
    # ------------------------------------------------------------------
    inputs_text = json.dumps(
        {
            "project_description": project_description[:256],
            "requirements": requirements[:10],
            "constraints": constraints,
        },
        sort_keys=True,
    )
    inputs_hash = hashlib.sha256(inputs_text.encode()).hexdigest()[:32]

    audit_row = AuditRow(
        trace_id=trace_id,
        timestamp=datetime.now(UTC),
        principal_id=auth_ctx.principal_id,
        module="team_assembler",
        inputs_hash=inputs_hash,
        retrieved_chunk_ids=[m["employee_id"] for m in team_members],
        prompt_version="team-assembler-v1",
        model_version=model_version,
        output_ref=f"team:{trace_id}",
        grounding_score=None,
        tenant=f"internal:{org}",
    )
    await get_audit_sink().append_async(audit_row)

    return result
