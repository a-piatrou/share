"""AI Team Assembler — Module 3 of GHOSTWIRE.

Analyzes a project description, scores candidates using skill matching AND
behavioral/feedback signals (AC-3 cross-edge from the Feedback Intelligence Engine),
and assembles an optimal team with full explainability (AC-5).

Public surface: ``assemble_team`` async function consumed by the team router.
"""

from app.team_assembler.service import assemble_team

__all__ = ["assemble_team"]
