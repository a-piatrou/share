"""Tier-1 assertion: the app imports the FROZEN types and does NOT redefine them.

Proves the single-source-of-truth discipline: the objects re-exported from app.contracts are
the *same objects* defined in system/contracts/stubs/shared_interfaces.py (identity check, not
just structural equality), and the frozen constants are unchanged. Any drift (a local redefinition
shadowing the contract) makes this fail. Run via `python -m tests.assert_frozen_types`.
"""

from __future__ import annotations

import importlib
import sys


def main() -> int:
    # Import the frozen stub directly (app.contracts puts the stub dir on sys.path).
    import app.contracts as c  # noqa: F401  ensures sys.path is set up

    frozen = importlib.import_module("shared_interfaces")

    checks: list[tuple[str, bool]] = []

    # Identity: every shared type/accessor in app.contracts IS the frozen object.
    shared_names = [
        "AuthContext",
        "AuditRow",
        "AuditSink",
        "DomainFilter",
        "RetrievedChunk",
        "KnowledgeCore",
        "EmbeddingService",
        "EmployeeIntelligenceProfile",
        "EmployeeRepository",
        "Review",
        "EvidenceRef",
        "FeedbackAnalysis",
        "FeedbackIntelligence",
        "PUBLIC_AUTH_CONTEXT",
    ]
    for name in shared_names:
        same = getattr(c, name) is getattr(frozen, name)
        checks.append((f"app.contracts.{name} IS frozen.{name}", same))

    # Frozen constants unchanged.
    checks.append(("EMBED_MODEL", c.EMBED_MODEL == "sentence-transformers/all-MiniLM-L6-v2"))
    checks.append(("EMBED_DIM", c.EMBED_DIM == 384))
    checks.append(("GROUNDING_THRESHOLD", c.GROUNDING_THRESHOLD == 0.7))
    checks.append(
        (
            "PUBLIC_DOMAINS",
            c.PUBLIC_DOMAINS == frozenset({"company", "case_studies", "job_openings"}),
        )
    )
    checks.append(
        (
            "PUBLIC_AUTH_CONTEXT.allowed_tenants",
            c.PUBLIC_AUTH_CONTEXT.allowed_tenants == frozenset({"public"}),
        )
    )

    # The concrete impls satisfy the frozen runtime-checkable Protocols.
    from app.knowledge_core import (
        get_embedding_service,
        get_employee_repository,
        get_feedback_intelligence,
        get_knowledge_core,
    )
    from app.shared_security import get_audit_sink

    checks.append(("KnowledgeCore impl", isinstance(get_knowledge_core(), frozen.KnowledgeCore)))
    checks.append(
        ("EmbeddingService impl", isinstance(get_embedding_service(), frozen.EmbeddingService))
    )
    checks.append(
        (
            "EmployeeRepository impl",
            isinstance(get_employee_repository(), frozen.EmployeeRepository),
        )
    )
    checks.append(
        (
            "FeedbackIntelligence impl",
            isinstance(get_feedback_intelligence(), frozen.FeedbackIntelligence),
        )
    )
    checks.append(("AuditSink impl", isinstance(get_audit_sink(), frozen.AuditSink)))

    ok = True
    for label, passed in checks:
        if not passed:
            ok = False
            print(f"  FAIL: {label}")
        else:
            print(f"  OK: {label}")
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
