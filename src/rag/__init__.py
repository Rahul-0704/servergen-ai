"""
ServerGen AI — RAG Knowledge Subsystem.

Provides durable document management, parsing, chunking, local embeddings,
hybrid semantic + keyword retrieval, and citation verification for local LLM inference.
"""

from src.rag.chunker import DocumentChunker
from src.rag.embeddings import (
    BaseEmbeddingProvider,
    LocalDeterministicEmbeddingProvider,
    OllamaEmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
)
from src.rag.indexer import DocumentIndexer
from src.rag.retriever import RoleFilteredRetriever
from src.rag.schemas import (
    CitationItem,
    DocumentCategory,
    KnowledgeChunk,
    KnowledgeDocument,
    RAGRetrievalResult,
)
from src.rag.service import DocumentService
from src.rag.storage import DocumentStorage
from src.rag.store import KnowledgeStore
from src.rag.verifier import CitationVerifier

__all__ = [
    "BaseEmbeddingProvider",
    "CitationItem",
    "CitationVerifier",
    "DocumentCategory",
    "DocumentChunker",
    "DocumentIndexer",
    "DocumentService",
    "DocumentStorage",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeStore",
    "LocalDeterministicEmbeddingProvider",
    "OllamaEmbeddingProvider",
    "RAGRetrievalResult",
    "RoleFilteredRetriever",
    "cosine_similarity",
    "get_embedding_provider",
]
