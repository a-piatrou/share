"""RBAC bridge + API-layer guard (defense-in-depth layer 1).

``build_auth_context`` is the FROZEN single bridge from a bearer token to an ``AuthContext``;
it is the ONLY place a token becomes tenants/domains. Every authenticated endpoint obtains its
AuthContext from here and never hand-constructs one. ``require_auth`` is the FastAPI dependency
that enforces role membership at the API layer (layer 1); the retrieval layer re-enforces
tenant/domain scoping inside KnowledgeCore.semantic_search (layer 2). Both layers are required.

## Bearer-token scheme (MVP, documented)
For the local demo we use a simple static mapping instead of a real IdP/JWT. The bearer token
is one of a small set of demo tokens of the form ``<role>-<org>`` (org optional for public):

    demo-admin-godeltech     -> role=admin    (full internal access for that org)
    demo-manager-godeltech   -> role=manager
    demo-employee-godeltech  -> role=employee
    demo-candidate           -> role=candidate (public-only)
    <no / unknown token>     -> role=public   (public-only; equals PUBLIC_AUTH_CONTEXT)

Role -> tenant/domain mapping (the RBAC policy):
    public     : tenants={public}                 domains=PUBLIC_DOMAINS
    candidate  : tenants={public}                 domains=PUBLIC_DOMAINS
    employee   : tenants={public, internal:<org>} domains=PUBLIC_DOMAINS + {employee_profiles,
                                                          project_requirements}
    manager    : tenants={public, internal:<org>} domains=PUBLIC_DOMAINS + {employee_profiles,
                                                          feedback, project_requirements}
    admin      : tenants={public, internal:<org>} domains=ALL_DOMAINS

This is intentionally swappable: Phase-2/3 can replace the body with real JWT-claim parsing
without changing the signature or any caller. The shape (role/org/allowed_tenants/
allowed_domains) is frozen in shared_interfaces.py.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.contracts import (
    PUBLIC_AUTH_CONTEXT,
    PUBLIC_DOMAINS,
    AuthContext,
    Domain,
    Role,
    Tenant,
)

ALL_DOMAINS: frozenset[Domain] = frozenset(
    {
        "company",
        "case_studies",
        "job_openings",
        "employee_profiles",
        "feedback",
        "project_requirements",
    }
)

# Internal (PII-bearing) domains beyond the public set, by role.
_INTERNAL_BASE: frozenset[Domain] = frozenset({"employee_profiles", "project_requirements"})
_MANAGER_DOMAINS: frozenset[Domain] = _INTERNAL_BASE | {"feedback"}

# Static demo token registry. Real deployments replace this with IdP/JWT verification.
_DEMO_TOKENS: dict[str, tuple[Role, str | None]] = {
    "demo-admin-godeltech": ("admin", "godeltech"),
    "demo-manager-godeltech": ("manager", "godeltech"),
    "demo-employee-godeltech": ("employee", "godeltech"),
    "demo-candidate": ("candidate", None),
    "demo-public": ("public", None),
}


class AuthError(Exception):
    """Raised when a token is structurally present but not recognized."""


def _internal_tenant(org: str | None) -> frozenset[Tenant]:
    return frozenset({f"internal:{org}"}) if org else frozenset()


def _context_for(role: Role, org: str | None) -> AuthContext:
    """Apply the RBAC policy: role(+org) -> allowed tenants/domains."""
    if role == "public" or role == "candidate":
        return AuthContext(
            principal_id=role,
            role=role,
            org=org,
            allowed_tenants=frozenset({"public"}),
            allowed_domains=PUBLIC_DOMAINS,
        )

    tenants = frozenset({"public"}) | _internal_tenant(org)
    if role == "employee":
        domains = PUBLIC_DOMAINS | _INTERNAL_BASE
    elif role == "manager":
        domains = PUBLIC_DOMAINS | _MANAGER_DOMAINS
    elif role == "admin":
        domains = ALL_DOMAINS
    else:  # defensive: unknown role collapses to public
        return PUBLIC_AUTH_CONTEXT

    principal = f"{role}:{org}" if org else role
    return AuthContext(
        principal_id=principal,
        role=role,
        org=org,
        allowed_tenants=tenants,
        allowed_domains=domains,
    )


def build_auth_context(bearer_token: str | None) -> AuthContext:
    """FROZEN RBAC bridge: the ONLY token -> AuthContext path.

    No token (or an unknown one) maps to the public context — the structural expression of
    REQ-013 (public surface on the PII-free tenant). A recognized demo token maps to its
    role/org via the documented policy above.
    """
    if not bearer_token:
        return PUBLIC_AUTH_CONTEXT
    token = bearer_token.strip()
    entry = _DEMO_TOKENS.get(token)
    if entry is None:
        # Unknown token: do not silently grant; treat as unauthenticated public principal.
        return PUBLIC_AUTH_CONTEXT
    role, org = entry
    return _context_for(role, org)


# --- API-layer guard (FastAPI dependency) ---

_bearer_scheme = HTTPBearer(auto_error=False)


def require_auth(roles: frozenset[Role] | set[Role] | None = None):
    """Build a FastAPI dependency enforcing RBAC at the API layer.

    Usage::

        @router.post("/feedback/analyze", dependencies=[Depends(require_auth({"manager","admin"}))])

    or to receive the AuthContext::

        async def handler(ctx: AuthContext = Depends(require_auth({"manager","admin"}))): ...

    Resolves the principal via the frozen ``build_auth_context`` bridge, then checks the
    principal's role against ``roles``. If ``roles`` is None, any (incl. public) principal is
    allowed. The retrieval layer still re-enforces tenant/domain scoping regardless.
    """
    allowed: frozenset[Role] | None = frozenset(roles) if roles else None

    async def _dep(
        creds: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    ) -> AuthContext:
        token = creds.credentials if creds else None
        ctx = build_auth_context(token)
        if allowed is not None and ctx.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="RBAC denied for this principal/tenant",
            )
        return ctx

    return _dep
