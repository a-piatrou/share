"""The shared brain: embeddings, Weaviate retrieval, employee + feedback persistence.

Every module reaches these through the frozen accessors (AC-4 discipline):
``get_embedding_service`` / ``get_knowledge_core`` / ``get_employee_repository`` /
``get_feedback_intelligence`` — never by instantiating the private impls directly.
"""

from app.knowledge_core.embedding import EmbeddingServiceImpl, get_embedding_service
from app.knowledge_core.employees import EmployeeRepositoryImpl, get_employee_repository
from app.knowledge_core.feedback import (
    FeedbackIntelligenceImpl,
    get_feedback_intelligence,
)
from app.knowledge_core.weaviate_core import (
    WeaviateKnowledgeCore,
    get_knowledge_core,
    get_weaviate_client,
)

__all__ = [
    "EmbeddingServiceImpl",
    "get_embedding_service",
    "WeaviateKnowledgeCore",
    "get_knowledge_core",
    "get_weaviate_client",
    "EmployeeRepositoryImpl",
    "get_employee_repository",
    "FeedbackIntelligenceImpl",
    "get_feedback_intelligence",
]
