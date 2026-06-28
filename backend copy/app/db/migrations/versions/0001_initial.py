"""initial schema: documents, employees, reviews, feedback_analyses, audit_rows

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-27

Hand-authored to mirror app.db.models (autogenerate needs a live DB). Kept in sync with the ORM.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("doc_id", sa.String(64), primary_key=True),
        sa.Column("domain", sa.String(32), nullable=False, index=True),
        sa.Column("tenant", sa.String(64), nullable=False, server_default="public", index=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
    )
    op.create_table(
        "employees",
        sa.Column("employee_id", sa.String(32), primary_key=True),
        sa.Column("org", sa.String(64), nullable=False, server_default="godeltech", index=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("cv_text", sa.Text, nullable=False),
        sa.Column("skills", sa.JSON, nullable=False),
        sa.Column("project_history", sa.JSON, nullable=False),
        sa.Column("availability", sa.String(64), nullable=True),
    )
    op.create_table(
        "reviews",
        sa.Column("review_id", sa.String(32), primary_key=True),
        sa.Column("employee_id", sa.String(32), nullable=False, index=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
    )
    op.create_table(
        "feedback_analyses",
        sa.Column("analysis_id", sa.String(64), primary_key=True),
        sa.Column("employee_id", sa.String(32), nullable=False, index=True),
        sa.Column("org", sa.String(64), nullable=False, server_default="godeltech", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("feedback_score", sa.Float, nullable=False),
        sa.Column("sentiment", sa.Float, nullable=False),
        sa.Column("confidence_score", sa.Float, nullable=False),
        sa.Column("strengths", sa.JSON, nullable=False),
        sa.Column("weaknesses", sa.JSON, nullable=False),
        sa.Column("risks", sa.JSON, nullable=False),
        sa.Column("team_dynamics_signals", sa.JSON, nullable=False),
    )
    op.create_table(
        "audit_rows",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("trace_id", sa.String(64), nullable=False, index=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("principal_id", sa.String(128), nullable=False),
        sa.Column("module", sa.String(32), nullable=False),
        sa.Column("inputs_hash", sa.String(128), nullable=False),
        sa.Column("retrieved_chunk_ids", sa.JSON, nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("output_ref", sa.String(256), nullable=False),
        sa.Column("grounding_score", sa.Float, nullable=True),
        sa.Column("tenant", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("audit_rows")
    op.drop_table("feedback_analyses")
    op.drop_table("reviews")
    op.drop_table("employees")
    op.drop_table("documents")
