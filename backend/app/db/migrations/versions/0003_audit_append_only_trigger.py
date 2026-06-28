"""audit append-only: enforce with a trigger (REVOKE is bypassed by the table owner)

Revision ID: 0003_audit_append_only_trigger
Revises: 0002_audit_append_only
Create Date: 2026-06-28

0002 REVOKEd UPDATE/DELETE from the app role, but the app connects as the table OWNER
(POSTGRES_USER=ghostwire), and owners bypass GRANT/REVOKE — so updates still succeeded. A
BEFORE UPDATE/DELETE/TRUNCATE trigger that RAISEs enforces append-only for EVERY role, owner
included. This is the real REQ-012 / GDPR audit-integrity guarantee. Postgres-only.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0003_audit_append_only_trigger"
down_revision: str | None = "0002_audit_append_only"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_rows_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_rows is append-only: % is not permitted', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER audit_rows_no_update_delete "
        "BEFORE UPDATE OR DELETE ON audit_rows "
        "FOR EACH ROW EXECUTE FUNCTION audit_rows_append_only();"
    )
    op.execute(
        "CREATE TRIGGER audit_rows_no_truncate "
        "BEFORE TRUNCATE ON audit_rows "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_rows_append_only();"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS audit_rows_no_truncate ON audit_rows;")
    op.execute("DROP TRIGGER IF EXISTS audit_rows_no_update_delete ON audit_rows;")
    op.execute("DROP FUNCTION IF EXISTS audit_rows_append_only();")
