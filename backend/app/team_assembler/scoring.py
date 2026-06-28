"""Candidate scoring for the AI Team Assembler (AC-3 + AC-5).

match_score Weighting (must sum to 1.0):
  - skill_match:      0.35  — cosine similarity between candidate skill vector and
                              required-skill vector (via shared EmbeddingService).
  - feedback_score:   0.30  — FeedbackAnalysis.feedback_score [0,1] from the
                              FeedbackIntelligence cross-edge (THE AC-3 hook: mutating
                              a candidate's feedback corpus changes this weight and
                              therefore changes their selection rank).
  - experience_fit:   0.20  — rule-based: count of project_history entries, capped at 1.0.
  - availability:     0.10  — binary (available=1.0, busy=0.0, unknown=0.5).
  - team_compat:      0.05  — low-burnout / low-conflict bonus from feedback risks.

The feedback_score weight (0.30) is large enough that a swing from 0.0 to 1.0 in a
candidate's feedback_score shifts match_score by ±0.30, which is sufficient to flip
selection order between close candidates — satisfying the corpus-mutation requirement of AC-3.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.contracts import EmployeeIntelligenceProfile, FeedbackAnalysis

# ---------------------------------------------------------------------------
# Weight constants — document all here so AC-3 corpus-mutation intent is clear.
# ---------------------------------------------------------------------------
W_SKILL = 0.35
W_FEEDBACK = 0.30  # AC-3: feedback_score materially drives selection
W_EXPERIENCE = 0.20
W_AVAILABILITY = 0.10
W_COMPAT = 0.05

_TOTAL_WEIGHT = W_SKILL + W_FEEDBACK + W_EXPERIENCE + W_AVAILABILITY + W_COMPAT
assert abs(_TOTAL_WEIGHT - 1.0) < 1e-9, f"Weights must sum to 1.0, got {_TOTAL_WEIGHT}"

# How many project_history entries are considered "full" experience (caps at 1.0).
_EXPERIENCE_FULL = 5


@dataclass
class ScoredCandidate:
    profile: EmployeeIntelligenceProfile
    analysis: FeedbackAnalysis | None
    match_score: float
    skill_score: float
    feedback_score: float
    experience_score: float
    availability_score: float
    compat_score: float


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def _skill_score(
    candidate_skills: list[str],
    candidate_vec: list[float],
    required_vec: list[float],
    required_skills: list[str],
) -> float:
    """Blend keyword overlap with embedding cosine similarity.

    50% discrete overlap (required skills present in candidate) + 50% cosine on
    the dense vectors so partial semantic matches also contribute.
    """
    if not required_skills:
        return 0.5  # no requirements stated -> neutral

    # Keyword overlap component.
    req_set = {s.lower() for s in required_skills}
    cand_set = {s.lower() for s in candidate_skills}
    overlap = len(req_set & cand_set) / len(req_set) if req_set else 0.0

    # Embedding cosine component.
    cos_sim = _cosine(candidate_vec, required_vec)

    return max(0.0, min(1.0, 0.5 * overlap + 0.5 * cos_sim))


def _experience_score(profile: EmployeeIntelligenceProfile) -> float:
    """Rule-based: more project_history entries => higher score, capped at 1.0."""
    count = len(profile.project_history)
    return min(1.0, count / _EXPERIENCE_FULL)


def _availability_score(profile: EmployeeIntelligenceProfile) -> float:
    """Binary availability signal from the profile's availability field."""
    avail = (profile.availability or "").lower().strip()
    if not avail or avail in {"unknown", "tbd", ""}:
        return 0.5
    # Negative keywords.
    if any(kw in avail for kw in ("busy", "unavailable", "on leave", "full", "booked")):
        return 0.0
    # Positive keywords.
    if any(kw in avail for kw in ("available", "open", "ready", "yes", "true")):
        return 1.0
    # Partial capacity keywords.
    if any(kw in avail for kw in ("partial", "limited", "half")):
        return 0.5
    return 0.5


def _compat_score(analysis: FeedbackAnalysis | None) -> float:
    """Team-compatibility bonus based on feedback risk severity.

    High burnout/conflict risk -> lower compatibility -> lower score.
    No analysis -> neutral 0.5.
    """
    if analysis is None:
        return 0.5

    penalty = 0.0
    for risk in analysis.risks:
        severity = risk.get("severity", "low")
        rtype = risk.get("type", "")
        # Burnout and conflict directly hurt team composition.
        if rtype in ("burnout", "conflict"):
            if severity == "high":
                penalty += 0.3
            elif severity == "medium":
                penalty += 0.15
            else:
                penalty += 0.05

    return max(0.0, min(1.0, 1.0 - penalty))


def score_candidate(
    profile: EmployeeIntelligenceProfile,
    analysis: FeedbackAnalysis | None,
    candidate_skill_vec: list[float],
    required_skill_vec: list[float],
    required_skills: list[str],
) -> ScoredCandidate:
    """Compute composite match_score for a single candidate.

    AC-3 hook: feedback_score weight (W_FEEDBACK=0.30) means that if the Feedback
    Intelligence corpus is mutated so an employee's feedback_score changes by 0.5,
    their match_score shifts by 0.15 — enough to change selection rank.

    When analysis is None (no feedback record exists), the feedback_score component
    defaults to 0.0, so the candidate is ranked lower unless their other signals are
    strong enough. This is intentional: missing behavioral data is a risk, not neutral.
    """
    skill = _skill_score(
        profile.skills,
        candidate_skill_vec,
        required_skill_vec,
        required_skills,
    )

    # AC-3 cross-edge: use the FeedbackIntelligence score directly.
    fb_score = analysis.feedback_score if analysis is not None else 0.0

    experience = _experience_score(profile)
    availability = _availability_score(profile)
    compat = _compat_score(analysis)

    total = (
        W_SKILL * skill
        + W_FEEDBACK * fb_score
        + W_EXPERIENCE * experience
        + W_AVAILABILITY * availability
        + W_COMPAT * compat
    )
    total = max(0.0, min(1.0, total))

    return ScoredCandidate(
        profile=profile,
        analysis=analysis,
        match_score=total,
        skill_score=skill,
        feedback_score=fb_score,
        experience_score=experience,
        availability_score=availability,
        compat_score=compat,
    )
