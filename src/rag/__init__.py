"""
ServerGen AI — RAG Knowledge Subsystem.

Provides role-filtered organizational knowledge retrieval for local LLM inference.
"""

from src.rag.retriever import RoleFilteredRetriever
from src.rag.schemas import DocumentCategory, KnowledgeChunk, KnowledgeDocument, RAGRetrievalResult
from src.rag.store import KnowledgeStore

__all__ = [
    "DocumentCategory",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeStore",
    "RAGRetrievalResult",
    "RoleFilteredRetriever",
]
