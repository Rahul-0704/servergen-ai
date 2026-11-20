"""
ServerGen AI — Document Ingestion & Background Indexing Worker.

Manages parsing, chunking, local embedding generation, and atomic vector
persistence. Handles safe retries, idempotent reindexing, and crash recovery.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.document import (
    ChunkEmbedding,
    Document,
    DocumentChunk,
    DocumentStatus,
    DocumentVersion,
    IndexingJob,
    IndexingJobStatus,
)
from src.rag.chunker import DocumentChunker
from src.rag.embeddings import get_embedding_provider
from src.rag.parsers import get_parser
from src.rag.storage import DocumentStorage
from src.services.audit_service import AuditEventType, AuditService

logger = logging.getLogger("servergen.rag.indexer")


class DocumentIndexer:
    """
    Executes parsing, chunking, and embedding workflows against durable document versions.
    """

    def __init__(self, db: AsyncSession, storage: DocumentStorage | None = None) -> None:
        self.db = db
        self.storage = storage or DocumentStorage()
        self.chunker = DocumentChunker()
        self.embedding_provider = get_embedding_provider()
        self.audit = AuditService(db)

    async def run_indexing_job(self, job_id: uuid.UUID) -> bool:
        """
        Execute an indexing job to completion.
        Returns True if indexing succeeded, False if failed.
        """
        # Load job
        res = await self.db.execute(select(IndexingJob).where(IndexingJob.id == job_id))
        job = res.scalar_one_or_none()
        if not job:
            logger.error("IndexingJob %s not found", job_id)
            return False

        # Load version and document
        res_v = await self.db.execute(
            select(DocumentVersion).where(DocumentVersion.id == job.version_id)
        )
        version = res_v.scalar_one_or_none()
        if not version:
            job.status = IndexingJobStatus.FAILED
            job.error_message = "DocumentVersion record not found"
            await self.db.commit()
            return False

        res_d = await self.db.execute(select(Document).where(Document.id == job.document_id))
        doc = res_d.scalar_one_or_none()
        if not doc:
            job.status = IndexingJobStatus.FAILED
            job.error_message = "Parent Document record not found"
            await self.db.commit()
            return False

        # Mark job and version in progress
        job.status = IndexingJobStatus.PROCESSING
        job.started_at = datetime.now(UTC)
        job.attempts += 1
        version.indexing_status = IndexingJobStatus.PROCESSING
        doc.status = DocumentStatus.PROCESSING
        await self.db.commit()

        await self.audit.record(
            event_type=AuditEventType.DOCUMENT_INDEXING_STARTED,
            action="document_indexing_started",
            request_id=str(job.id),
            decision="allow",
            resource=f"document/{doc.id}/version/{version.version_number}",
            metadata={
                "document_id": str(doc.id),
                "version_id": str(version.id),
                "filename": version.original_filename,
                "attempt": job.attempts,
            },
        )

        try:
            # 1. Read original file
            file_bytes = self.storage.read_file(version.storage_path)

            # 2. Select parser and extract text
            parser = get_parser(version.original_filename, version.mime_type)
            parsed = parser.parse(file_bytes, version.original_filename)

            # 3. Structure-aware chunking
            chunks = self.chunker.chunk_blocks(parsed.blocks)
            if not chunks:
                msg = "Document yielded zero valid text chunks after parsing"
                raise ValueError(msg)

            # 4. Generate embeddings
            chunk_texts = [c.content for c in chunks]
            vectors = await self.embedding_provider.embed_batch(chunk_texts)

            # 5. Idempotent cleanup: delete any existing chunks/embeddings for this version
            await self.db.execute(
                delete(DocumentChunk).where(DocumentChunk.version_id == version.id)
            )

            # 6. Insert new chunks and embeddings
            doc_vault = (getattr(doc, "vault_scope", "all") or "all").lower()
            for idx, (chunk_item, vec) in enumerate(zip(chunks, vectors, strict=False)):
                chunk_record = DocumentChunk(
                    id=uuid.uuid4(),
                    document_id=doc.id,
                    version_id=version.id,
                    vault_scope=doc_vault,
                    chunk_index=idx,
                    content=chunk_item.content,
                    token_count=chunk_item.token_count,
                    page_number=chunk_item.page_number,
                    section_heading=chunk_item.section_heading,
                    chunk_metadata=chunk_item.metadata,
                )
                self.db.add(chunk_record)
                await self.db.flush()

                embedding_record = ChunkEmbedding(
                    id=uuid.uuid4(),
                    chunk_id=chunk_record.id,
                    embedding_model=self.embedding_provider.model_name,
                    dimensions=len(vec),
                    embedding_vector=vec,
                )
                self.db.add(embedding_record)

            # 7. Update version record
            version.parser_used = parsed.parser_name
            version.extracted_character_count = parsed.total_characters
            version.chunk_count = len(chunks)
            version.indexing_status = IndexingJobStatus.COMPLETED
            version.error_message = None

            # 8. Update parent document record
            doc.status = DocumentStatus.INDEXED
            doc.active_version_id = version.id

            # 9. Update job record
            job.status = IndexingJobStatus.COMPLETED
            job.completed_at = datetime.now(UTC)
            job.error_message = None

            await self.db.commit()

            await self.audit.record(
                event_type=AuditEventType.DOCUMENT_INDEXING_COMPLETED,
                action="document_indexing_completed",
                request_id=str(job.id),
                decision="allow",
                resource=f"document/{doc.id}/version/{version.version_number}",
                metadata={
                    "document_id": str(doc.id),
                    "version_id": str(version.id),
                    "chunks_indexed": len(chunks),
                    "embedding_model": self.embedding_provider.model_name,
                    "dimensions": len(vectors[0]) if vectors else 0,
                },
            )
            logger.info(
                "Successfully indexed document '%s' v%d (%d chunks)",
                doc.title,
                version.version_number,
                len(chunks),
            )
            return True

        except Exception as exc:
            err_msg = str(exc)
            logger.error("Indexing failed for job %s: %s", job.id, err_msg)

            job.status = IndexingJobStatus.FAILED
            job.error_message = err_msg
            version.indexing_status = IndexingJobStatus.FAILED
            version.error_message = err_msg

            # Only mark parent doc failed if no other version is active
            if doc.active_version_id is None or doc.active_version_id == version.id:
                doc.status = DocumentStatus.FAILED

            await self.db.commit()

            await self.audit.record(
                event_type=AuditEventType.DOCUMENT_INDEXING_FAILED,
                action="document_indexing_failed",
                request_id=str(job.id),
                decision="error",
                resource=f"document/{doc.id}/version/{version.version_number}",
                metadata={"error": err_msg, "document_id": str(doc.id)},
            )
            return False

    @staticmethod
    async def recover_stale_jobs(db: AsyncSession) -> int:
        """
        Scan for interrupted jobs (status == 'processing') from application restarts
        and mark them eligible for retry.
        """
        stmt = (
            update(IndexingJob)
            .where(IndexingJob.status == IndexingJobStatus.PROCESSING)
            .values(
                status=IndexingJobStatus.QUEUED,
                error_message="Recovered after application restart",
            )
        )
        res = await db.execute(stmt)
        await db.commit()
        return res.rowcount
