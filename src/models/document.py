"""
ServerGen AI — Persistent Document & Knowledge Models.

SQLAlchemy 2.x models for durable enterprise document storage, versions,
structural chunks, embeddings, indexing jobs, and granular document permissions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from src.models.user import User


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"
    DELETED = "deleted"


class IndexingJobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class Document(TimestampMixin, Base):
    """
    Enterprise knowledge document entity.
    Tracks lifecycle, ownership, classification, and permissions.
    """

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_status_classification", "status", "classification"),
        Index("ix_documents_owner", "owner_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=generate_uuid
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="general", index=True)
    classification: Mapped[str] = mapped_column(
        String(50), nullable=False, default="internal", index=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    allowed_roles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    vault_scope: Mapped[str] = mapped_column(
        String(50), nullable=False, default="all", index=True
    )
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=DocumentStatus.PENDING, index=True
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    versions: Mapped[list[DocumentVersion]] = relationship(
        "DocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number",
        lazy="selectin",
    )
    permissions: Mapped[list[DocumentPermission]] = relationship(
        "DocumentPermission",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    chunks: Mapped[list[DocumentChunk]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    jobs: Mapped[list[IndexingJob]] = relationship(
        "IndexingJob",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    owner: Mapped[User | None] = relationship("User", foreign_keys=[owner_id], lazy="selectin")

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, title={self.title!r}, status={self.status})>"


class DocumentVersion(TimestampMixin, Base):
    """
    Immutable version of an uploaded document file.
    Tracks storage reference, checksum, parser metadata, and indexing health.
    """

    __tablename__ = "document_versions"
    __table_args__ = (
        Index("ix_document_versions_doc_ver", "document_id", "version_number", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=generate_uuid
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    parser_used: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    extracted_character_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    indexing_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=IndexingJobStatus.QUEUED, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    document: Mapped[Document] = relationship("Document", back_populates="versions")
    chunks: Mapped[list[DocumentChunk]] = relationship(
        "DocumentChunk",
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index",
        lazy="selectin",
    )
    jobs: Mapped[list[IndexingJob]] = relationship(
        "IndexingJob",
        back_populates="version",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentVersion(id={self.id}, doc_id={self.document_id}, v={self.version_number})>"
        )


class DocumentChunk(Base):
    """
    Extracted textual chunk from a document version.
    Includes structural boundaries (page, section heading) and metadata.
    """

    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_chunks_doc_version", "document_id", "version_id"),
        Index("ix_chunks_version_index", "version_id", "chunk_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=generate_uuid
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_heading: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    vault_scope: Mapped[str] = mapped_column(
        String(50), nullable=False, default="all", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    document: Mapped[Document] = relationship("Document", back_populates="chunks")
    version: Mapped[DocumentVersion] = relationship("DocumentVersion", back_populates="chunks")
    embedding: Mapped[ChunkEmbedding | None] = relationship(
        "ChunkEmbedding",
        back_populates="chunk",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<DocumentChunk(id={self.id}, doc_id={self.document_id}, idx={self.chunk_index})>"


class ChunkEmbedding(Base):
    """
    Vector embedding representation of a document chunk.
    Persists embedding vectors alongside model identification and dimension metadata.
    """

    __tablename__ = "chunk_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=generate_uuid
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_vector: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    chunk: Mapped[DocumentChunk] = relationship("DocumentChunk", back_populates="embedding")

    def __repr__(self) -> str:
        return (
            f"<ChunkEmbedding(chunk_id={self.chunk_id}, "
            f"model={self.embedding_model}, dim={self.dimensions})>"
        )


class IndexingJob(TimestampMixin, Base):
    """
    Asynchronous document parsing, chunking, and embedding job tracker.
    Provides idempotent processing, recovery of interrupted jobs, and error logs.
    """

    __tablename__ = "indexing_jobs"
    __table_args__ = (Index("ix_indexing_jobs_version", "version_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=generate_uuid
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=IndexingJobStatus.QUEUED, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    document: Mapped[Document] = relationship("Document", back_populates="jobs")
    version: Mapped[DocumentVersion] = relationship("DocumentVersion", back_populates="jobs")

    def __repr__(self) -> str:
        return f"<IndexingJob(id={self.id}, ver_id={self.version_id}, status={self.status})>"


class DocumentPermission(Base):
    """
    Explicit document-level access grant for individual users or specific roles.
    """

    __tablename__ = "document_permissions"
    __table_args__ = (Index("ix_doc_perms_grantee", "grantee_type", "grantee_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=generate_uuid
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    grantee_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "role" or "user"
    grantee_id: Mapped[str] = mapped_column(String(100), nullable=False)  # role name or user UUID
    permission_level: Mapped[str] = mapped_column(String(20), nullable=False, default="read")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    document: Mapped[Document] = relationship("Document", back_populates="permissions")

    def __repr__(self) -> str:
        return (
            f"<DocumentPermission(doc_id={self.document_id}, "
            f"{self.grantee_type}={self.grantee_id})>"
        )
