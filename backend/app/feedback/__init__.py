"""Feedback Intelligence Engine — Phase-2 implementation.

Owned by the feedback-builder worktree.  Exposes ``analyze_reviews`` which drives
a real LLM analysis via the shared ClaudeClient, enforces AC-2 (every item MUST
carry an evidence_ref whose review_id is a real input review id), computes the
deterministic feedback_score, persists the result so team_assembler's
``FeedbackIntelligence.get_async`` can read it, and writes an append-only AuditRow.
"""

from app.feedback.service import analyze_reviews

__all__ = ["analyze_reviews"]
