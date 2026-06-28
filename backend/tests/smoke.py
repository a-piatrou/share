"""Docker-dependent SMOKE test (best effort). Requires postgres + weaviate + t2v up and migrated.

Run via `python -m tests.smoke` (or `make smoke`). Asserts:
  1. GET /health == 200 {status: ok}.
  2. semantic_search on PUBLIC_AUTH_CONTEXT returns ONLY public-tenant / PII-free chunks
     (no employee_profiles / feedback / internal tenant — REQ-013).
  3. semantic_search on PUBLIC_AUTH_CONTEXT for an explicitly internal domain returns [] (the
     RBAC retrieval layer cannot be coaxed into PII).
  4. EmployeeRepository.list_candidates (admin ctx) returns the seeded employees.
  5. FeedbackIntelligence.get path works for a seeded employee.
Exits non-zero on any failure.
"""

from __future__ import annotations

import sys

from fastapi.testclient import TestClient

from app.contracts import (
    PUBLIC_AUTH_CONTEXT,
    AuthContext,
    DomainFilter,
)
from app.knowledge_core import (
    get_employee_repository,
    get_feedback_intelligence,
    get_knowledge_core,
)
from app.main import app

ADMIN_CTX = AuthContext(
    principal_id="smoke-admin",
    role="admin",
    org="godeltech",
    allowed_tenants=frozenset({"public", "internal:godeltech"}),
    allowed_domains=frozenset(
        {
            "company",
            "case_studies",
            "job_openings",
            "employee_profiles",
            "feedback",
            "project_requirements",
        }
    ),
)

_PII_FREE = {"company", "case_studies", "job_openings"}


def main() -> int:
    ok = True

    def check(label: str, passed: bool) -> None:
        nonlocal ok
        if passed:
            print(f"  OK: {label}")
        else:
            ok = False
            print(f"  FAIL: {label}")

    # 1. health
    with TestClient(app) as client:
        resp = client.get("/health")
        check("GET /health == 200", resp.status_code == 200)
        check("health body status==ok", resp.json().get("status") == "ok")

    core = get_knowledge_core()

    # 2. public semantic_search returns ONLY public/PII-free chunks
    chunks = core.semantic_search(
        "What does GHOSTWIRE do and what roles are open?",
        DomainFilter(domains=PUBLIC_AUTH_CONTEXT.allowed_domains),
        PUBLIC_AUTH_CONTEXT,
        k=5,
    )
    check("public search returns >=1 chunk", len(chunks) >= 1)
    check("all chunks on public tenant", all(c.tenant == "public" for c in chunks))
    check("all chunks PII-free domain", all(c.domain in _PII_FREE for c in chunks))

    # 3. public context cannot retrieve internal domains even if asked
    leaked = core.semantic_search(
        "employee performance feedback",
        DomainFilter(domains=frozenset({"employee_profiles", "feedback"})),
        PUBLIC_AUTH_CONTEXT,
        k=5,
    )
    check("public context yields NO internal chunks", leaked == [])

    # 4. EmployeeRepository.list_candidates (admin) returns seeded employees
    repo = get_employee_repository()
    candidates = repo.list_candidates(ADMIN_CTX)
    ids = {c.employee_id for c in candidates}
    check("list_candidates returns >=6 employees", len(candidates) >= 6)
    check("seeded ids present", {"E001", "E004"}.issubset(ids))

    # public principal sees NO candidates (RBAC)
    check("public principal sees no candidates", repo.list_candidates(PUBLIC_AUTH_CONTEXT) == [])

    # 5. FeedbackIntelligence.get path works
    fi = get_feedback_intelligence()
    fa = fi.get("E004", ADMIN_CTX)
    check("feedback get(E004) returns an analysis", fa is not None)
    if fa is not None:
        check("feedback_score in [0,1]", 0.0 <= fa.feedback_score <= 1.0)
        check("E004 carries a risk signal (burnout/conflict seed)", len(fa.risks) >= 1)

    print("SMOKE RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
