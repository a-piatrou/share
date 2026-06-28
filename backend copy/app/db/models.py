"""SQLAlchemy 2 ORM models for the structured (PostgreSQL) side of the brain.

- Document / Employee / Review hold the seed corpus's structured form.
- FeedbackAnalysisRow persists the latest FeedbackAnalysis per employee (the cross-edge the
  team_assembler consumes via FeedbackIntelligence.get()).
- AuditRow is APPEND-ONLY: there is NO update/delete code path anywhere in the app, and the
  audit NFR is reinforced at the DB grant level (see the audit-grants migration). The ORM
  model exists for inserts + reads only.

JSON-typed columns use the portable ``JSON`` type so the same models work under SQLite in
tests (no Postgres needed for tier-1) and Postgres at runtime.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DocumentORM(Base):
    """A public-tenant document chunk (company / case_studies / job_openings). PII-free."""

    __tablename__ = "documents"

    doc_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    domain: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, default="public", index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class EmployeeORM(Base):
    """Structured employee profile (internal tenant). Maps to EmployeeIntelligenceProfile."""

    __tablename__ = "employees"

    employee_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    org: Mapped[str] = mapped_column(String(64), nullable=False, default="godeltech", index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    cv_text: Mapped[str] = mapped_column(Text, nullable=False)
    skills: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    project_history: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    availability: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ReviewORM(Base):
    """A peer/manager/self review (internal tenant). Input to FeedbackIntelligence."""

    __tablename__ = "reviews"

    review_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    employee_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # peer|manager|self
    text: Mapped[str] = mapped_column(Text, nullable=False)


class FeedbackAnalysisRowORM(Base):
    """Persisted latest FeedbackAnalysis per employee (the team_assembler cross-edge).

    The structured sub-objects (strengths/weaknesses/risks/team_dynamics_signals) are stored
    as JSON; the persistence layer serializes/deserializes the frozen FeedbackAnalysis dataclass.
    """

    __tablename__ = "feedback_analyses"

    analysis_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    employee_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    org: Mapped[str] = mapped_column(String(64), nullable=False, default="godeltech", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True
    )
    feedback_score: Mapped[float] = mapped_column(Float, nullable=False)
    sentiment: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    strengths: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    weaknesses: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    risks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    team_dynamics_signals: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class AuditRowORM(Base):
    """Append-only AI-decision audit record (AuditRow). INSERT + SELECT only.

    No UPDATE/DELETE code path exists; the audit-grants migration revokes UPDATE/DELETE at the
    DB role level so append-only is enforced below the application as well.
    """

    __tablename__ = "audit_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    principal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    module: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # chatbot|feedback|team_assembler
    inputs_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    retrieved_chunk_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    output_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    grounding_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    tenant: Mapped[str | None] = mapped_column(String(64), nullable=True)
