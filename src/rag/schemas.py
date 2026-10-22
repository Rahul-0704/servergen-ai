"""
ServerGen AI — RAG Knowledge Schemas.

Defines schemas for organizational documents, chunks, and retrieval results
with embedded data sensitivity and role-based access control metadata.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
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
    allowed_roles: list[str] = Field(default_factory=list, description="Roles permitted to access this document")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeChunk(BaseModel):
    """A retrieval chunk with access control metadata."""

    chunk_id: str
    doc_id: uuid.UUID
    doc_title: str
    content: str
    category: DocumentCategory
    classification: DataSensitivity
    allowed_roles: list[str]
    relevance_score: float = 0.0


class RAGRetrievalResult(BaseModel):
    """Result of role-filtered knowledge retrieval."""

    chunks: list[KnowledgeChunk] = Field(default_factory=list)
    total_searched: int = 0
    denied_chunks_count: int = 0
    highest_sensitivity: DataSensitivity = DataSensitivity.PUBLIC
    context_text: str = ""
