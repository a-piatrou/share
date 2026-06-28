"""Seed ingestion: load system/seed/ into Postgres + Weaviate (deterministic ids).

Run as a module after `alembic upgrade head` and with the datastores up::

    .venv/bin/python -m app.knowledge_core.ingest

What it does:
  Postgres (structured side):
    - documents      <- public_docs.json
    - employees      <- employees.json
    - reviews        <- reviews.json
    - feedback_analyses: runs FeedbackIntelligence.analyze() per employee so get() works and the
      team_assembler cross-edge is populated (deterministic Phase-1 stub).
  Weaviate (vector side, one multi-tenant KnowledgeChunk collection):
    - tenant "public"           <- public docs ONLY (PII-free; company/case_studies/job_openings).
    - tenant "internal:<org>"   <- employee_profiles + project_requirements + feedback chunks.
    Weaviate vectorizes every object with the text2vec-transformers module (same model the app's
    EmbeddingService uses), so query/document vectors are comparable.

Idempotent: upserts by primary key (Postgres) and deletes+reinserts the collection objects per
source_id is avoided — instead it skips Weaviate insert if the collection already has objects for
a tenant unless --force is passed. Safe to re-run after a fresh `docker compose up` + migrate.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.contracts import SEED_DIR, AuthContext, Review
from app.db.models import DocumentORM, EmployeeORM, ReviewORM
from app.db.session import async_session_factory
from app.knowledge_core.feedback import get_feedback_intelligence
from app.knowledge_core.weaviate_core import (
    COLLECTION,
    PUBLIC_TENANT,
    ensure_schema,
    ensure_tenants,
    get_weaviate_client,
    internal_tenant,
    wv_tenant,
)

DEFAULT_ORG = "godeltech"

# An admin AuthContext used by the ingestion script to populate feedback analyses (full internal
# access). Built via the policy, not hand-rolled tenants beyond what the script legitimately owns.
_INGEST_CTX = AuthContext(
    principal_id="ingest",
    role="admin",
    org=DEFAULT_ORG,
    allowed_tenants=frozenset({"public", f"internal:{DEFAULT_ORG}"}),
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


def _load(name: str):
    with open(SEED_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


async def _ingest_postgres() -> dict[str, int]:
    docs = _load("public_docs.json")
    employees = _load("employees.json")
    reviews = _load("reviews.json")
    counts = {"documents": 0, "employees": 0, "reviews": 0, "feedback_analyses": 0}

    async with async_session_factory() as session:
        for d in docs:
            existing_doc = await session.get(DocumentORM, d["doc_id"])
            if existing_doc is None:
                session.add(
                    DocumentORM(
                        doc_id=d["doc_id"],
                        domain=d["domain"],
                        tenant="public",
                        title=d["title"],
                        text=d["text"],
                    )
                )
                counts["documents"] += 1
        for e in employees:
            existing_emp = await session.get(EmployeeORM, e["employee_id"])
            if existing_emp is None:
                session.add(
                    EmployeeORM(
                        employee_id=e["employee_id"],
                        org=DEFAULT_ORG,
                        name=e["name"],
                        cv_text=e["cv_text"],
                        skills=e["skills"],
                        project_history=e["project_history"],
                        availability=e.get("availability"),
                    )
                )
                counts["employees"] += 1
        for r in reviews:
            existing_review = await session.get(ReviewORM, r["review_id"])
            if existing_review is None:
                session.add(
                    ReviewORM(
                        review_id=r["review_id"],
                        employee_id=r["employee_id"],
                        kind=r["kind"],
                        text=r["text"],
                    )
                )
                counts["reviews"] += 1
        await session.commit()

    # Populate feedback analyses so FeedbackIntelligence.get() works for team_assembler.
    by_emp: dict[str, list[Review]] = {}
    for r in reviews:
        by_emp.setdefault(r["employee_id"], []).append(
            Review(
                review_id=r["review_id"],
                employee_id=r["employee_id"],
                kind=r["kind"],
                text=r["text"],
            )
        )
    fi = get_feedback_intelligence()
    for rv in by_emp.values():
        await fi.analyze_async(rv, _INGEST_CTX, org=DEFAULT_ORG)
        counts["feedback_analyses"] += 1
    return counts


def _ingest_weaviate(force: bool = False) -> dict[str, int]:
    docs = _load("public_docs.json")
    employees = _load("employees.json")
    projects = _load("project_requirements.json")

    ensure_schema()
    internal = internal_tenant(DEFAULT_ORG)
    ensure_tenants([PUBLIC_TENANT, internal])

    client = get_weaviate_client()
    coll = client.collections.get(COLLECTION)
    counts = {"public": 0, "internal": 0}

    # PUBLIC tenant: PII-free docs only.
    pub = coll.with_tenant(wv_tenant(PUBLIC_TENANT))
    if force or pub.aggregate.over_all(total_count=True).total_count == 0:
        with pub.batch.dynamic() as batch:
            for d in docs:
                batch.add_object(
                    properties={
                        "source_id": d["doc_id"],
                        "text": d["text"],
                        "domain": d["domain"],
                        "tenant": PUBLIC_TENANT,
                        "title": d["title"],
                    }
                )
                counts["public"] += 1

    # INTERNAL tenant: employee profiles + project requirements (PII-bearing).
    intc = coll.with_tenant(wv_tenant(internal))
    if force or intc.aggregate.over_all(total_count=True).total_count == 0:
        with intc.batch.dynamic() as batch:
            for e in employees:
                profile_text = (
                    f"{e['name']}. Skills: {', '.join(e['skills'])}. {e['cv_text']} "
                    f"Projects: {'; '.join(e['project_history'])}."
                )
                batch.add_object(
                    properties={
                        "source_id": f"EMP-{e['employee_id']}",
                        "text": profile_text,
                        "domain": "employee_profiles",
                        "tenant": internal,
                        "title": e["name"],
                    }
                )
                counts["internal"] += 1
            for p in projects:
                batch.add_object(
                    properties={
                        "source_id": f"PROJ-{p['project_id']}",
                        "text": f"{p['title']}. {p['description']} Required skills: "
                        f"{', '.join(p['required_skills'])}.",
                        "domain": "project_requirements",
                        "tenant": internal,
                        "title": p["title"],
                    }
                )
                counts["internal"] += 1
    return counts


async def run(force: bool = False) -> None:
    import structlog

    log = structlog.get_logger()
    pg = await _ingest_postgres()
    log.info("ingest.postgres", **pg)
    wv = _ingest_weaviate(force=force)
    log.info("ingest.weaviate", **wv)
    print("Postgres:", pg)
    print("Weaviate:", wv)


def main() -> int:
    import asyncio

    parser = argparse.ArgumentParser(description="GHOSTWIRE seed ingestion")
    parser.add_argument(
        "--force", action="store_true", help="re-insert Weaviate objects even if present"
    )
    args = parser.parse_args()
    asyncio.run(run(force=args.force))
    return 0


if __name__ == "__main__":
    sys.exit(main())
