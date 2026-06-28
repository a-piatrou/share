"""Public RAG chatbot (Module 1).

Grounded answers only, on the PII-free public tenant. The router (app.routers.chat) is the HTTP
surface; this package owns the pipeline (intent -> retrieve -> grounded Claude call ->
grounding/abstain + citation-resolution -> audit). Everything routes through the SHARED brain
accessors (get_knowledge_core / get_audit_sink) and the shared Claude client (AC-4 discipline).
"""

from app.chatbot.intent import detect_intent, domain_filter_for
from app.chatbot.service import ChatResult, answer_query

__all__ = ["answer_query", "ChatResult", "detect_intent", "domain_filter_for"]
