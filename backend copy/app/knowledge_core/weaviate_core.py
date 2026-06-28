"""KnowledgeCore over Weaviate — the shared retrieval brain (multi-tenant, RBAC-scoped).

## Tenancy model (the gdpr-rbac-guardrail RBAC layer-2)
ONE multi-tenant collection ``KnowledgeChunk`` with a ``domain`` property. Tenants:
- ``public``           — holds ONLY PII-free domains (company / case_studies / job_openings).
- ``internal:<org>``   — holds employee_profiles / feedback / project_requirements for that org.

``semantic_search`` is scoped TWICE by the AuthContext, so retrieval itself cannot leak:
1. **tenant scope** — it only ever queries tenants in ``auth_ctx.allowed_tenants``. The public
   chatbot (PUBLIC_AUTH_CONTEXT) has allowed_tenants == {"public"}, so it physically cannot
   read any internal tenant (REQ-013).
2. **domain scope** — it filters to ``domain_filter.domains ∩ auth_ctx.allowed_domains``. If
   the intersection is empty, it returns [] (a normal abstain path, not an error).

Hybrid (BM25 + dense) search is used; Weaviate vectorizes the query with the same
text2vec-transformers module, so query and document vectors are comparable. The returned
RetrievedChunk carries the tenant + domain so callers/audit can verify scoping.
"""

from __future__ import annotations

import threading

from app.config import get_settings
from app.contracts import (
    PUBLIC_DOMAINS,
    AuthContext,
    Domain,
    DomainFilter,
    RetrievedChunk,
    Tenant,
)

COLLECTION = "KnowledgeChunk"
PUBLIC_TENANT: Tenant = "public"

# Which domains are allowed to live in which tenant kind. Enforced at ingestion AND used as a
# defensive post-filter on read so a misconfigured corpus can never surface PII on a public read.
_PUBLIC_TENANT_DOMAINS: frozenset[Domain] = PUBLIC_DOMAINS


def internal_tenant(org: str) -> Tenant:
    return f"internal:{org}"


def wv_tenant(tenant: Tenant) -> str:
    """Map a LOGICAL tenant name to a Weaviate-safe PHYSICAL name.

    Weaviate tenant names allow only [A-Za-z0-9_-]; our logical convention 'internal:<org>'
    contains a ':' which Weaviate rejects (422). The logical name stays the source of truth in
    AuthContext / audit rows; only the physical Weaviate tenant uses this mapping. Applied at
    every Weaviate tenant boundary (create + query + ingest write)."""
    return tenant.replace(":", "__")


# --- Weaviate client singleton (v4) -----------------------------------------------------------

_client = None
_client_lock = threading.Lock()


def get_weaviate_client():
    """Return a connected weaviate v4 client (lazy singleton).

    Imported lazily so importing this module never requires a running Weaviate (tier-1 boot).
    """
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        import weaviate

        s = get_settings()
        _client = weaviate.connect_to_local(
            host=s.weaviate_host,
            port=s.weaviate_http_port,
            grpc_port=s.weaviate_grpc_port,
        )
        return _client


def close_weaviate_client() -> None:
    global _client
    if _client is not None:
        try:
            _client.close()
        finally:
            _client = None


def ensure_schema() -> None:
    """Create the multi-tenant KnowledgeChunk collection if absent (idempotent)."""
    from weaviate.classes.config import Configure, DataType, Property

    client = get_weaviate_client()
    if client.collections.exists(COLLECTION):
        return
    client.collections.create(
        name=COLLECTION,
        vectorizer_config=Configure.Vectorizer.text2vec_transformers(),
        multi_tenancy_config=Configure.multi_tenancy(enabled=True),
        properties=[
            Property(name="source_id", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="text", data_type=DataType.TEXT),
            Property(name="domain", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="tenant", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="title", data_type=DataType.TEXT),
        ],
    )


def ensure_tenants(tenants: list[Tenant]) -> None:
    """Create the given tenants on the collection if absent (idempotent)."""
    from weaviate.classes.tenants import Tenant as WTenant

    client = get_weaviate_client()
    coll = client.collections.get(COLLECTION)
    existing = set(coll.tenants.get().keys())  # physical names
    to_add = [WTenant(name=wv_tenant(t)) for t in tenants if wv_tenant(t) not in existing]
    if to_add:
        coll.tenants.create(to_add)


# --- KnowledgeCore ----------------------------------------------------------------------------


class WeaviateKnowledgeCore:
    """Concrete KnowledgeCore (satisfies the KnowledgeCore Protocol)."""

    def semantic_search(
        self,
        query: str,
        domain_filter: DomainFilter,
        auth_ctx: AuthContext,
        k: int = 5,
    ) -> list[RetrievedChunk]:
        # Domain scope: only domains BOTH requested AND allowed for this principal.
        allowed_domains = frozenset(domain_filter.domains) & frozenset(auth_ctx.allowed_domains)
        if not allowed_domains or not auth_ctx.allowed_tenants:
            return []  # nothing this principal may see for this filter -> normal abstain path

        from weaviate.classes.query import Filter, MetadataQuery

        client = get_weaviate_client()
        coll = client.collections.get(COLLECTION)
        existing_tenants = set(coll.tenants.get().keys())  # physical names

        domain_filter_w = Filter.by_property("domain").contains_any(list(allowed_domains))

        results: list[RetrievedChunk] = []
        # Query EACH allowed tenant separately (Weaviate scopes a query to one tenant) and merge.
        for tenant in auth_ctx.allowed_tenants:  # logical names
            phys = wv_tenant(tenant)
            if phys not in existing_tenants:
                continue
            tcoll = coll.with_tenant(phys)
            resp = tcoll.query.hybrid(
                query=query,
                alpha=0.5,  # balance BM25 (0) and dense (1)
                limit=k,
                filters=domain_filter_w,
                return_metadata=MetadataQuery(score=True),
            )
            for obj in resp.objects:
                props = obj.properties
                domain = str(props.get("domain", ""))
                # Defense-in-depth: never surface a non-public domain on the public tenant, and
                # never return a domain outside the principal's allowed set even if the corpus
                # were misconfigured.
                if tenant == PUBLIC_TENANT and domain not in _PUBLIC_TENANT_DOMAINS:
                    continue
                if domain not in allowed_domains:
                    continue
                score = (
                    obj.metadata.score if obj.metadata and obj.metadata.score is not None else 0.0
                )
                results.append(
                    RetrievedChunk(
                        source_id=str(props.get("source_id", "")),
                        text=str(props.get("text", "")),
                        score=float(score),
                        tenant=tenant,  # type: ignore[arg-type]
                        domain=domain,  # type: ignore[arg-type]
                    )
                )

        # Merge across tenants by score, return top-k.
        results.sort(key=lambda c: c.score, reverse=True)
        return results[:k]


_core: WeaviateKnowledgeCore | None = None


def get_knowledge_core() -> WeaviateKnowledgeCore:
    """The single shared KnowledgeCore accessor (AC-4 discipline)."""
    global _core
    if _core is None:
        _core = WeaviateKnowledgeCore()
    return _core
