"""Public RAG chatbot router (chatbot module owner).

POST /chat/query — PUBLIC (security:[] in the frozen OpenAPI): the endpoint uses ONLY the frozen
PUBLIC_AUTH_CONTEXT (PII-free public tenant, REQ-013); it takes no bearer token. It returns a
schema-valid RAGAnswer (grounded or abstaining) and echoes the audit trace_id in the X-Trace-Id
response header. The grounding/abstain + citation-resolution + audit logic lives in
app.chatbot.service; this module is the thin HTTP envelope.

NOTE for integration: this router is NOT yet mounted in app.main — the lead wires
``app.include_router(chat.router)`` there.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from app.chatbot.service import answer_query
from app.observability import span

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatQueryRequest(BaseModel):
    """Mirrors the frozen OpenAPI /chat/query request body (additionalProperties:false)."""

    model_config = {"extra": "forbid"}

    query: str = Field(..., description="The user's question.")
    session_id: str | None = Field(default=None, description="Optional client session id.")


class Citation(BaseModel):
    model_config = {"extra": "forbid"}

    source_id: str
    snippet: str


class RAGAnswerResponse(BaseModel):
    """Mirrors system/contracts/schemas/rag_answer.schema.json (the response body is also
    schema-validated inside the Claude client; this model documents the OpenAPI surface)."""

    model_config = {"extra": "forbid"}

    answer: str
    citations: list[Citation]
    intent: str
    confidence: float
    abstained: bool


@router.post("/query", response_model=RAGAnswerResponse)
async def query(req: ChatQueryRequest, response: Response) -> dict:
    """Grounded public answer or abstention. Always returns a valid RAGAnswer; sets X-Trace-Id."""
    trace_id = uuid.uuid4().hex
    with span("chatbot.query", trace_id=trace_id, has_session=req.session_id is not None):
        result = await answer_query(req.query, trace_id)
    # Correlate this decision to its append-only AuditRow (X-Trace-Id, per the frozen OpenAPI).
    response.headers["X-Trace-Id"] = result.trace_id
    return result.answer
