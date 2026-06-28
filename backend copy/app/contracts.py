"""Single source of truth for the FROZEN shared interfaces.

The frozen contract lives in ``system/contracts/stubs/shared_interfaces.py`` and is
READ-ONLY. To guarantee zero drift, the backend does NOT redefine any of those types — it
inserts the stub directory onto ``sys.path`` once and re-exports everything from the frozen
module. Every other module in the app imports the shared types from ``app.contracts`` (or
directly from ``shared_interfaces``); the concrete implementations in
``app.shared_security`` / ``app.knowledge_core`` build the real backing for the Protocols and
accessors declared here.
"""

from __future__ import annotations

import sys
from pathlib import Path

# .../backend/app/contracts.py -> repo root is parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
_STUB_DIR = _REPO_ROOT / "system" / "contracts" / "stubs"
if str(_STUB_DIR) not in sys.path:
    sys.path.insert(0, str(_STUB_DIR))

# Re-export the frozen contract verbatim. This is the ONLY place the stub is imported;
# everything else imports from here so there is exactly one definition of each shape.
from shared_interfaces import (  # type: ignore  # noqa: E402,F401,F403
    EMBED_DIM,
    EMBED_MODEL,
    GROUNDING_THRESHOLD,
    INTENT_DOMAINS,
    PUBLIC_AUTH_CONTEXT,
    PUBLIC_DOMAINS,
    AuditRow,
    AuditSink,
    AuthContext,
    Domain,
    DomainFilter,
    EmbeddingService,
    EmployeeIntelligenceProfile,
    EmployeeRepository,
    EvidenceRef,
    FeedbackAnalysis,
    FeedbackIntelligence,
    KnowledgeCore,
    RetrievedChunk,
    Review,
    Role,
    Tenant,
    Vector,
    build_auth_context,  # NOTE: stub raises NotImplementedError; the real impl is in
    get_audit_sink,  # app.shared_security / app.knowledge_core and is what the app uses.
    get_embedding_service,
    get_employee_repository,
    get_feedback_intelligence,
    get_knowledge_core,
)

# Convenience: where the seed corpus lives (used by the ingestion script).
SEED_DIR = _REPO_ROOT / "system" / "seed"

__all__ = [
    "EMBED_DIM",
    "EMBED_MODEL",
    "GROUNDING_THRESHOLD",
    "INTENT_DOMAINS",
    "PUBLIC_AUTH_CONTEXT",
    "PUBLIC_DOMAINS",
    "AuditRow",
    "AuditSink",
    "AuthContext",
    "Domain",
    "DomainFilter",
    "EmbeddingService",
    "EmployeeIntelligenceProfile",
    "EmployeeRepository",
    "EvidenceRef",
    "FeedbackAnalysis",
    "FeedbackIntelligence",
    "KnowledgeCore",
    "RetrievedChunk",
    "Review",
    "Role",
    "Tenant",
    "Vector",
    "build_auth_context",
    "get_audit_sink",
    "get_embedding_service",
    "get_employee_repository",
    "get_feedback_intelligence",
    "get_knowledge_core",
    "SEED_DIR",
]
