"""FROZEN shared-interface contract for GHOSTWIRE (contract_version 1).

Source of truth for the signatures every module builds against. Feature worktrees import
THESE shapes and call THESE accessors; the knowledge-core-builder implements the real backing
in the app package mirroring them exactly. Changing anything here is a contract change: only
the contract-lead may edit it, and a change bumps contract_version in project_state.json.

Stubs only — no behavior. Real implementations live in the app's backend package. Pins SHAPE
and the single shared entrypoints, not behavior: ranking, tenant scoping, <2s latency, and the
empty-result/abstain semantics are validated at the Phase-3 runtime gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional, Protocol, runtime_checkable

Vector = list[float]
Role = Literal["public", "candidate", "employee", "manager", "admin"]
Tenant = str  # "public" or "internal:<org>"
Domain = Literal[
    "company", "case_studies", "job_openings",
    "employee_profiles", "feedback", "project_requirements",
]

# --- Frozen embedding contract (one model/dim across ALL modules — prevents incomparable
# vectors and keeps employee data in-VPC for GDPR; local model, no external embedding API) ---
EMBED_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIM: int = 384

# PII-free domains the public chatbot may ever touch.
PUBLIC_DOMAINS: frozenset[Domain] = frozenset({"company", "case_studies", "job_openings"})

# Frozen intent -> retrieval-domain routing (REQ-006). All within the public PII-free set.
INTENT_DOMAINS: dict[str, frozenset[Domain]] = {
    "client": frozenset({"company", "case_studies"}),
    "candidate": frozenset({"job_openings", "company"}),
    "unknown": PUBLIC_DOMAINS,
}

GROUNDING_THRESHOLD: float = 0.7  # faithfulness in [0,1]; below OR no supporting chunk => abstain


# --- RBAC / audit (cross-cutting, owned by shared_security) ---

@dataclass(frozen=True)
class AuthContext:
    """Propagated on EVERY semantic_search call. Maps the principal to the tenants/domains
    retrieval may touch. The public chatbot is restricted to allowed_tenants == {"public"}."""
    principal_id: str
    role: Role
    org: Optional[str]
    allowed_tenants: frozenset[Tenant]
    allowed_domains: frozenset[Domain]


def build_auth_context(bearer_token: Optional[str]) -> AuthContext:
    """FROZEN RBAC bridge: the ONLY way a bearer token becomes an AuthContext. Maps the token's
    role/org claims to allowed_tenants/allowed_domains. shared_security owns the real impl;
    every authenticated endpoint MUST obtain its AuthContext from here (never hand-construct one)."""
    raise NotImplementedError  # implemented in app shared_security


# The single frozen public context. /chat/query MUST use exactly this — it is the structural
# expression of REQ-013 (public chatbot on a PII-free tenant). Phase-3 RBAC gate asserts no
# employee_profiles/feedback chunk can ever be returned on this context.
PUBLIC_AUTH_CONTEXT: AuthContext = AuthContext(
    principal_id="public",
    role="public",
    org=None,
    allowed_tenants=frozenset({"public"}),
    allowed_domains=PUBLIC_DOMAINS,
)


@dataclass(frozen=True)
class AuditRow:
    """Append-only AI-decision audit record. Correlates with the OTel trace_id. Written for
    every RAG answer, feedback analysis, and team selection."""
    trace_id: str
    timestamp: datetime
    principal_id: str
    module: Literal["chatbot", "feedback", "team_assembler"]
    inputs_hash: str
    retrieved_chunk_ids: list[str]
    prompt_version: str
    model_version: str
    output_ref: str
    grounding_score: Optional[float]
    tenant: Optional[Tenant]


@runtime_checkable
class AuditSink(Protocol):
    """Append-only sink. No update/delete — enforced at the DDL (no UPDATE/DELETE grants)."""
    def append(self, row: AuditRow) -> None: ...


# --- Knowledge Core (the shared brain) ---

@dataclass(frozen=True)
class DomainFilter:
    domains: frozenset[Domain]


@dataclass(frozen=True)
class RetrievedChunk:
    source_id: str
    text: str
    score: float
    tenant: Tenant
    domain: Domain


@runtime_checkable
class KnowledgeCore(Protocol):
    def semantic_search(
        self, query: str, domain_filter: DomainFilter, auth_ctx: AuthContext, k: int = 5
    ) -> list[RetrievedChunk]:
        """Hybrid (BM25+dense) retrieval over Weaviate, tenant-scoped by auth_ctx. MUST NOT
        return chunks outside auth_ctx.allowed_tenants / allowed_domains. Returning [] (no
        match) is a NORMAL abstain path, not an error — the caller sets abstained=true."""
        ...


@runtime_checkable
class EmbeddingService(Protocol):
    def embed(self, texts: list[str]) -> list[Vector]:
        """Single shared embedding path (EMBED_MODEL/EMBED_DIM). No per-module duplicates (AC-4)."""
        ...


# --- Employee Intelligence Profile + repository accessor (team_assembler reads structured
# profiles + enumerates candidates through THIS — not opaque chunks) ---

@dataclass(frozen=True)
class EmployeeIntelligenceProfile:
    employee_id: str
    name: str
    cv_text: str
    skills: list[str]
    feedback_summary: Optional[str]
    project_history: list[str]
    availability: Optional[str]


@runtime_checkable
class EmployeeRepository(Protocol):
    def get(self, employee_id: str, auth_ctx: AuthContext) -> Optional[EmployeeIntelligenceProfile]: ...
    def list_candidates(
        self, auth_ctx: AuthContext, required_skills: Optional[list[str]] = None
    ) -> list[EmployeeIntelligenceProfile]: ...


# --- Feedback Intelligence (consumed by team_assembler — the one real cross-edge) ---

@dataclass(frozen=True)
class Review:
    review_id: str
    employee_id: str
    kind: Literal["peer", "manager", "self"]
    text: str


@dataclass(frozen=True)
class EvidenceRef:
    review_id: str
    quote: str


@dataclass(frozen=True)
class FeedbackAnalysis:
    """Mirrors feedback_analysis.schema.json. Every item carries an EvidenceRef (AC-2).
    analysis_id is the resolvable record id that team feedback_signal_ref.source points at
    (AC-3). feedback_score is the DETERMINISTIC behavioral scalar the team scorer consumes —
    NOT confidence_score (which is confidence in the analysis itself)."""
    analysis_id: str
    employee_id: str
    feedback_score: float          # [0,1] deterministic; see glossary.feedback_score_formula
    sentiment: float               # [-1,1]
    strengths: list[tuple[str, EvidenceRef]]
    weaknesses: list[tuple[str, EvidenceRef]]
    risks: list[dict]              # {type, text, severity, evidence_ref}
    team_dynamics_signals: list[tuple[str, EvidenceRef]]
    confidence_score: float        # [0,1] confidence in THIS analysis (not behavioral quality)


@runtime_checkable
class FeedbackIntelligence(Protocol):
    def analyze(self, reviews: list[Review], auth_ctx: AuthContext) -> FeedbackAnalysis:
        """Analyze a review set AND PERSIST the result keyed by employee_id (so get() can return
        it later for the team_assembler cross-edge)."""
        ...
    def get(self, employee_id: str, auth_ctx: AuthContext) -> Optional[FeedbackAnalysis]:
        """Return the persisted latest analysis for an employee, or None."""
        ...


# --- Single concrete accessors all modules MUST call (AC-4: shared brain, no private dupes).
# shared_security/knowledge_core provide the real impls; importing the Protocol is NOT enough. ---

def get_knowledge_core() -> KnowledgeCore: raise NotImplementedError
def get_embedding_service() -> EmbeddingService: raise NotImplementedError
def get_employee_repository() -> EmployeeRepository: raise NotImplementedError
def get_feedback_intelligence() -> FeedbackIntelligence: raise NotImplementedError
def get_audit_sink() -> AuditSink: raise NotImplementedError


__all__ = [
    "Vector", "Role", "Tenant", "Domain",
    "EMBED_MODEL", "EMBED_DIM", "PUBLIC_DOMAINS", "INTENT_DOMAINS", "GROUNDING_THRESHOLD",
    "AuthContext", "build_auth_context", "PUBLIC_AUTH_CONTEXT", "AuditRow", "AuditSink",
    "DomainFilter", "RetrievedChunk", "KnowledgeCore", "EmbeddingService",
    "EmployeeIntelligenceProfile", "EmployeeRepository",
    "Review", "EvidenceRef", "FeedbackAnalysis", "FeedbackIntelligence",
    "get_knowledge_core", "get_embedding_service", "get_employee_repository",
    "get_feedback_intelligence", "get_audit_sink",
]
