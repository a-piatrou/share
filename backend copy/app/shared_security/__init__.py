"""Shared security library: RBAC bridge, API-layer guard, append-only audit sink.

This is the single cross-cutting library every module consumes (the gdpr-rbac-guardrail
mitigation). It owns:
- ``build_auth_context`` — the ONLY bearer-token -> AuthContext bridge.
- ``require_auth`` — the FastAPI API-layer RBAC dependency.
- ``AuditSink`` / ``get_audit_sink`` — the append-only AI-decision audit trail.
"""

from app.shared_security.audit import PostgresAuditSink, get_audit_sink
from app.shared_security.auth import (
    AuthError,
    build_auth_context,
    require_auth,
)

__all__ = [
    "build_auth_context",
    "require_auth",
    "AuthError",
    "PostgresAuditSink",
    "get_audit_sink",
]
