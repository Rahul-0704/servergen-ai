"""
ServerGen AI — RAG Knowledge & Retrieval Schemas.

Defines schemas for organizational documents, chunks, citations,
and retrieval results with embedded data sensitivity and role-based access control metadata.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from src.ai.schemas import DataSensitivity


class DocumentCategory(StrEnum):
    ARCHITECTURE = "architecture"
    OPERATIONS = "operations"
    SECURITY = "security"
    POLICY = "policy"
    EXECUTIVE = "executive"
    GENERAL = "general"


class KnowledgeDocument(BaseModel):
    """An organizational knowledge document."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    title: str
    content: str
    category: DocumentCategory = DocumentCategory.GENERAL
    classification: DataSensitivity = DataSensitivity.INTERNAL
    vault_scope: str = Field(
        default="all", description="Target vault scope ('all', 'manager', etc.)"
    )
    allowed_roles: list[str] = Field(
        default_factory=list,
        description="Roles permitted to access this document",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeChunk(BaseModel):
    """A retrieval chunk with access control metadata and relevance scoring."""

    chunk_id: str
    doc_id: uuid.UUID
    doc_title: str
    content: str
    category: DocumentCategory = DocumentCategory.GENERAL
    classification: DataSensitivity = DataSensitivity.INTERNAL
    vault_scope: str = Field(
        default="all", description="Target vault scope ('all', 'manager', etc.)"
    )
    allowed_roles: list[str] = Field(default_factory=list)
    relevance_score: float = 0.0
    semantic_score: float = 0.0
    keyword_score: float = 0.0
    rerank_score: float = 0.0
    page_number: int | None = None
    section_heading: str | None = None
    version_number: int = 1
    retrieval_method: str = "hybrid_rrf"


class CitationItem(BaseModel):
    """Verified source citation for grounded LLM answers."""

    citation_index: int
    document_id: str
    document_title: str
    version_number: int
    page_number: int | None = None
    section_heading: str | None = None
    classification: str
    vault_scope: str = "all"
    relevance_score: float = 0.0
    excerpt: str = ""
    is_verified: bool = True


class RAGRetrievalResult(BaseModel):
    """Result of role-filtered hybrid knowledge retrieval."""

    chunks: list[KnowledgeChunk] = Field(default_factory=list)
    total_searched: int = 0
    denied_chunks_count: int = 0
    highest_sensitivity: DataSensitivity = DataSensitivity.PUBLIC
    context_text: str = ""
    insufficient_evidence: bool = False
    retrieval_strategy: str = "hybrid_rrf"
    execution_time_ms: float = 0.0
    citations: list[CitationItem] = Field(default_factory=list)
