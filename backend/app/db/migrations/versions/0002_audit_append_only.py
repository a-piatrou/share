"""audit append-only: revoke UPDATE/DELETE on audit_rows from the app role

Revision ID: 0002_audit_append_only
Revises: 0001_initial
Create Date: 2026-06-27

Reinforces the audit NFR below the application: the app's DB role keeps INSERT + SELECT on
audit_rows but loses UPDATE and DELETE, so even a buggy/compromised code path cannot mutate the
AI-decision trail. Postgres-only (no-op on other dialects, e.g. SQLite in tests).
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0002_audit_append_only"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The app connects as this role (matches docker-compose POSTGRES_USER).
_APP_ROLE = "ghostwire"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(f"REVOKE UPDATE, DELETE ON TABLE audit_rows FROM {_APP_ROLE}")
    # Also revoke from PUBLIC so a future role cannot inherit the grant implicitly.
    op.execute("REVOKE UPDATE, DELETE ON TABLE audit_rows FROM PUBLIC")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(f"GRANT UPDATE, DELETE ON TABLE audit_rows TO {_APP_ROLE}")
