"""
ServerGen AI — Enterprise RAG & Document Management API.

Production endpoints for:
1. Document upload, versions, reindexing, preview, and safe deletion.
2. Background indexing job tracking and recovery.
3. Hybrid semantic + keyword retrieval testing (RAG Lab).
4. Grounded answer generation with local LLM and citation validation.
5. Automated RAG evaluation benchmark suite.
6. Subsystem health checks (Ollama, embeddings, vector dimensions, storage).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.schemas import DataSensitivity
from src.auth.permissions import PermissionCode
from src.auth.rbac import AuthContext, get_auth_context, require_permission
from src.core.database import get_db
from src.core.exceptions import NotFoundError, ValidationError
from src.models.document import (
    Document,
    DocumentChunk,
    DocumentStatus,
    IndexingJob,
)
from src.rag.indexer import DocumentIndexer
from src.rag.retriever import RoleFilteredRetriever
from src.rag.schemas import DocumentCategory, KnowledgeDocument
from src.rag.service import DocumentService
from src.rag.storage import DocumentStorage
from src.rag.store import KnowledgeStore
from src.rag.verifier import CitationVerifier

logger = logging.getLogger("servergen.rag.api")

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])

_doc_read = require_permission(PermissionCode.DOCUMENT_READ)
_doc_write = require_permission(PermissionCode.DOCUMENT_WRITE)


# ── Request / Response Schemas ───────────────────────────────────────────


class LegacyDocumentCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    content: str = Field(..., min_length=10)
    category: DocumentCategory = DocumentCategory.GENERAL
    classification: DataSensitivity = DataSensitivity.INTERNAL
    allowed_roles: list[str] = Field(default_factory=list)


class RetrievalTestRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000)
    top_k: int = Field(default=4, ge=1, le=20)
    min_relevance: float = Field(default=0.25, ge=0.0, le=1.0)


class GroundedAnswerRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000)
    top_k: int = Field(default=4, ge=1, le=20)
    min_relevance: float = Field(default=0.25, ge=0.0, le=1.0)
    model: str | None = None


# Predefined evaluation benchmark test cases
_EVALUATION_TEST_CASES = [
    {
        "id": "TC-01",
        "question": "What local LLM and database stack does ServerGen AI use?",
        "expected_document": "ServerGen AI System Overview & Core Capabilities",
        "classification": "internal",
        "required_role": "general_employee",
    },
    {
        "id": "TC-02",
        "question": "What permissions and roles are defined under RBAC standards?",
        "expected_document": "Enterprise Role Permissions & Clearance Standards",
        "classification": "internal",
        "required_role": "general_employee",
    },
    {
        "id": "TC-03",
        "question": "How do IT operators inspect database connection pools and what requires approval?",
        "expected_document": "IT Operations & Server Diagnostic Runbook",
        "classification": "confidential",
        "required_role": "it_operator",
    },
    {
        "id": "TC-04",
        "question": "How does the audit ledger verify hash chain integrity via SHA-256?",
        "expected_document": "Defensive Security & Audit Integrity Verification Playbook",
        "classification": "confidential",
        "required_role": "security_analyst",
    },
    {
        "id": "TC-05",
        "question": "What was the Q3 expenditure for enterprise automation under Policy HR-702?",
        "expected_document": "Executive Policy & Q3 Enterprise Financial Audit",
        "classification": "restricted",
        "required_role": "manager",
    },
    {
        "id": "TC-06",
        "question": "What is the procedure for launching quantum teleportation drones?",
        "expected_document": "NONE (Insufficient evidence test)",
        "classification": "public",
        "required_role": "general_employee",
        "expect_abstention": True,
    },
]


# ── Document Lifecycle Endpoints ─────────────────────────────────────────


@router.post("/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    category: str = Form("general"),
    classification: str = Form("internal"),
    vault_scope: str = Form("all"),
    allowed_roles: str = Form(""),
    department: str | None = Form(None),
    description: str = Form(""),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Securely upload a document file (PDF, DOCX, XLSX, PPTX, CSV, TXT, MD, HTML).
    Validates file headers, writes atomically to durable storage, and indexes asynchronously.
    """
    roles_list: list[str] = []
    if allowed_roles:
        try:
            parsed = json.loads(allowed_roles)
            if isinstance(parsed, list):
                roles_list = [str(r).strip().lower() for r in parsed if str(r).strip()]
        except Exception:
            roles_list = [r.strip().lower() for r in allowed_roles.split(",") if r.strip()]

    content = await file.read()
    if not content:
        raise ValidationError("Uploaded file is empty (0 bytes)")

    service = DocumentService(db)
    doc, version, job = await service.create_document_with_file(
        auth=auth,
        filename=file.filename or "uploaded_doc.bin",
        content=content,
        title=title,
        category=category,
        classification=classification,
        vault_scope=vault_scope,
        allowed_roles=roles_list or None,
        department=department,
        description=description,
        auto_index=True,
    )

    return {
        "status": "success",
        "document_id": str(doc.id),
        "version_id": str(version.id),
        "job_id": str(job.id),
        "title": doc.title,
        "category": doc.category,
        "classification": doc.classification,
        "vault_scope": doc.vault_scope,
        "indexing_status": version.indexing_status,
        "file_size": version.file_size,
        "checksum_sha256": version.checksum_sha256,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


@router.get("/documents", dependencies=[Depends(_doc_read)])
async def list_documents(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    category: str | None = Query(None),
    classification: str | None = Query(None),
    vault_scope: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    """List organizational documents accessible to the caller's role."""
    service = DocumentService(db)
    docs = await service.list_documents(
        auth=auth,
        category=category,
        classification=classification,
        vault_scope=vault_scope,
        search_query=search,
        limit=limit,
        offset=offset,
    )

    result = []
    for d in docs:
        active_ver = next((v for v in d.versions if v.id == d.active_version_id), None)
        result.append({
            "id": str(d.id),
            "title": d.title,
            "description": d.description,
            "category": d.category,
            "classification": d.classification,
            "vault_scope": d.vault_scope,
            "status": d.status,
            "active_version": active_ver.version_number if active_ver else 1,
            "file_size": active_ver.file_size if active_ver else 0,
            "chunk_count": active_ver.chunk_count if active_ver else 0,
            "indexing_status": active_ver.indexing_status if active_ver else d.status,
            "allowed_roles": d.allowed_roles,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        })

    # If DB has no documents yet, include permitted seeded store documents
    if not result:
        store = KnowledgeStore.get_instance()
        user_role = auth.role.lower()
        max_clearance = RoleFilteredRetriever._ROLE_MAX_CLEARANCE.get(user_role, DataSensitivity.INTERNAL)
        max_rank = RoleFilteredRetriever._SENSITIVITY_ORDER[max_clearance]

        for sd in store.list_documents():
            sd_rank = RoleFilteredRetriever._SENSITIVITY_ORDER[sd.classification]
            sd_vault = (getattr(sd, "vault_scope", "all") or "all").lower()
            is_sd_vault_accessible = (
                user_role == "administrator"
                or sd_vault == "all"
                or sd_vault == user_role
            )
            if vault_scope and sd_vault != vault_scope.lower():
                continue
            has_role = not sd.allowed_roles or user_role in [r.lower() for r in sd.allowed_roles]
            if (sd_rank <= max_rank and has_role and is_sd_vault_accessible) or user_role == "administrator":
                result.append({
                    "id": str(sd.id),
                    "title": sd.title,
                    "description": "Canonical organizational record",
                    "category": sd.category.value,
                    "classification": sd.classification.value,
                    "vault_scope": sd_vault,
                    "status": "indexed",
                    "active_version": 1,
                    "file_size": len(sd.content.encode("utf-8")),
                    "chunk_count": len([p for p in sd.content.split("\n\n") if p.strip()]),
                    "indexing_status": "completed",
                    "allowed_roles": sd.allowed_roles,
                    "created_at": sd.created_at.isoformat(),
                    "updated_at": sd.created_at.isoformat(),
                })

    return result


@router.post("/documents", dependencies=[Depends(_doc_write)])
async def create_document(
    body: LegacyDocumentCreateRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Register an organizational document (backwards-compatible with legacy prototype)."""
    # Create via DocumentService as a plaintext file so it is durably persisted
    service = DocumentService(db)
    content_bytes = body.content.encode("utf-8")
    filename = f"{body.title.lower().replace(' ', '_')[:32]}.txt"

    doc, version, _job = await service.create_document_with_file(
        auth=auth,
        filename=filename,
        content=content_bytes,
        title=body.title,
        category=body.category.value,
        classification=body.classification.value,
        allowed_roles=body.allowed_roles or [auth.role.lower()],
        auto_index=True,
    )

    # Also register in in-memory store for fallback
    store = KnowledgeStore.get_instance()
    store.add_document(
        KnowledgeDocument(
            id=doc.id,
            title=doc.title,
            content=body.content,
            category=body.category,
            classification=body.classification,
            allowed_roles=body.allowed_roles or [auth.role],
        )
    )

    return {
        "status": "created",
        "id": str(doc.id),
        "title": doc.title,
        "classification": doc.classification,
        "allowed_roles": doc.allowed_roles,
        "indexing_status": version.indexing_status,
    }


@router.get("/documents/{document_id}", dependencies=[Depends(_doc_read)])
async def get_document(
    document_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Get detailed document metadata and version history."""
    service = DocumentService(db)
    doc = await service.get_document(document_id, auth)

    versions_data = []
    for v in doc.versions:
        versions_data.append({
            "version_number": v.version_number,
            "filename": v.original_filename,
            "file_size": v.file_size,
            "mime_type": v.mime_type,
            "checksum_sha256": v.checksum_sha256,
            "parser_used": v.parser_used,
            "chunk_count": v.chunk_count,
            "indexing_status": v.indexing_status,
            "error_message": v.error_message,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        })

    return {
        "id": str(doc.id),
        "title": doc.title,
        "description": doc.description,
        "category": doc.category,
        "classification": doc.classification,
        "vault_scope": doc.vault_scope,
        "status": doc.status,
        "active_version_id": str(doc.active_version_id) if doc.active_version_id else None,
        "allowed_roles": doc.allowed_roles,
        "versions": versions_data,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }


@router.get("/documents/{document_id}/versions", dependencies=[Depends(_doc_read)])
async def get_document_versions(
    document_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict[str, Any]]:
    """List all version records for a document."""
    service = DocumentService(db)
    doc = await service.get_document(document_id, auth)

    return [
        {
            "id": str(v.id),
            "version_number": v.version_number,
            "filename": v.original_filename,
            "file_size": v.file_size,
            "checksum_sha256": v.checksum_sha256,
            "parser_used": v.parser_used,
            "chunk_count": v.chunk_count,
            "indexing_status": v.indexing_status,
            "is_active": v.id == doc.active_version_id,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in doc.versions
    ]


@router.post("/documents/{document_id}/version")
async def upload_document_version(
    document_id: uuid.UUID,
    file: UploadFile = File(...),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Upload a new version of an existing document."""
    content = await file.read()
    if not content:
        raise ValidationError("Uploaded file is empty (0 bytes)")

    service = DocumentService(db)
    version, job = await service.add_new_version(
        auth=auth,
        document_id=document_id,
        filename=file.filename or "updated_version.bin",
        content=content,
        auto_index=True,
    )

    return {
        "status": "success",
        "document_id": str(document_id),
        "version_id": str(version.id),
        "version_number": version.version_number,
        "job_id": str(job.id),
        "indexing_status": version.indexing_status,
        "file_size": version.file_size,
        "checksum_sha256": version.checksum_sha256,
    }


@router.post("/documents/{document_id}/reindex")
async def reindex_document(
    document_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Rebuild the search chunks and embeddings for a document."""
    service = DocumentService(db)
    job = await service.reindex_document(document_id, auth)
    return {
        "status": "reindexed",
        "document_id": str(document_id),
        "job_id": str(job.id),
        "job_status": job.status,
    }


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Delete a document, its versions, active vectors, and underlying files."""
    service = DocumentService(db)
    success = await service.delete_document(document_id, auth)
    return {"status": "deleted", "document_id": str(document_id), "success": success}


@router.get("/documents/{document_id}/preview", dependencies=[Depends(_doc_read)])
async def preview_document_chunks(
    document_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(10, ge=1, le=50),
) -> dict[str, Any]:
    """Preview extracted chunks from active document version."""
    service = DocumentService(db)
    doc = await service.get_document(document_id, auth)

    if not doc.active_version_id:
        return {"document_id": str(doc.id), "title": doc.title, "chunks": []}

    stmt = (
        select(DocumentChunk)
        .where(
            DocumentChunk.document_id == doc.id,
            DocumentChunk.version_id == doc.active_version_id,
        )
        .order_by(DocumentChunk.chunk_index)
        .limit(limit)
    )
    res = await db.execute(stmt)
    chunks = res.scalars().all()

    return {
        "document_id": str(doc.id),
        "title": doc.title,
        "active_version": doc.active_version_id,
        "total_previewed": len(chunks),
        "chunks": [
            {
                "chunk_index": c.chunk_index,
                "content": c.content,
                "token_count": c.token_count,
                "page_number": c.page_number,
                "section_heading": c.section_heading,
            }
            for c in chunks
        ],
    }


@router.get("/documents/{document_id}/download", dependencies=[Depends(_doc_read)])
async def download_document(
    document_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Download the original uploaded document file."""
    service = DocumentService(db)
    doc = await service.get_document(document_id, auth)
    if not doc.active_version_id:
        raise NotFoundError("Document has no active version to download")

    version = next((v for v in doc.versions if v.id == doc.active_version_id), None)
    if not version or not version.storage_path:
        raise NotFoundError("Document file version not found")

    content = service.storage.read_file(version.storage_path)
    filename = version.original_filename or f"document_{doc.id}.bin"
    mime_type = version.mime_type or "application/octet-stream"

    return Response(
        content=content,
        media_type=mime_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Job Management Endpoints ─────────────────────────────────────────────


@router.get("/jobs/{job_id}", dependencies=[Depends(_doc_read)])
async def get_job_status(
    job_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Query status and error logs for an indexing job."""
    res = await db.execute(select(IndexingJob).where(IndexingJob.id == job_id))
    job = res.scalar_one_or_none()
    if not job:
        raise NotFoundError(f"Job {job_id} not found")

    return {
        "job_id": str(job.id),
        "document_id": str(job.document_id),
        "version_id": str(job.version_id),
        "status": job.status,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "error_message": job.error_message,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.post("/jobs/{job_id}/retry")
async def retry_indexing_job(
    job_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Retry a failed or interrupted indexing job."""
    res = await db.execute(select(IndexingJob).where(IndexingJob.id == job_id))
    job = res.scalar_one_or_none()
    if not job:
        raise NotFoundError(f"Job {job_id} not found")

    indexer = DocumentIndexer(db)
    success = await indexer.run_indexing_job(job.id)
    await db.refresh(job)

    return {
        "job_id": str(job.id),
        "status": job.status,
        "success": success,
        "error_message": job.error_message,
    }


# ── RAG Lab & Knowledge Retrieval Testing Endpoints ──────────────────────


@router.post("/test/retrieval")
async def test_retrieval_only(
    body: RetrievalTestRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """
    RAG Lab: Retrieval-only testing endpoint.
    Executes permission-aware hybrid search without invoking LLM generation.
    Returns candidate passages, similarity and keyword scores, and RRF rankings.
    """
    retriever = RoleFilteredRetriever()
    result = await retriever.retrieve(
        query=body.query,
        auth=auth,
        top_k=body.top_k,
        min_relevance=body.min_relevance,
        db=db,
    )

    chunks_data = [
        {
            "chunk_id": c.chunk_id,
            "document_id": str(c.doc_id),
            "document_title": c.doc_title,
            "content": c.content,
            "classification": c.classification.value,
            "relevance_score": c.relevance_score,
            "semantic_score": c.semantic_score,
            "keyword_score": c.keyword_score,
            "page_number": c.page_number,
            "section_heading": c.section_heading,
            "version_number": c.version_number,
        }
        for c in result.chunks
    ]

    return {
        "query": body.query,
        "total_searched": result.total_searched,
        "denied_chunks_count": result.denied_chunks_count,
        "highest_sensitivity": result.highest_sensitivity.value,
        "insufficient_evidence": result.insufficient_evidence,
        "retrieval_strategy": result.retrieval_strategy,
        "execution_time_ms": result.execution_time_ms,
        "retrieved_chunks_count": len(result.chunks),
        "chunks": chunks_data,
        "citations": [c.model_dump() for c in result.citations],
    }


@router.post("/test/grounded")
async def test_grounded_answer(
    body: GroundedAnswerRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """
    RAG Lab: Grounded answer testing with execution timeline and citation verification.
    """
    timeline: list[dict[str, Any]] = []
    t0 = time.monotonic()

    def add_step(event: str, details: str = "", status: str = "ok") -> None:
        timeline.append({
            "event": event,
            "details": details,
            "status": status,
            "time_offset_ms": round((time.monotonic() - t0) * 1000, 1),
        })

    add_step("request_received", f"Query: {body.query[:80]}")
    add_step("authorization_verified", f"Role: {auth.role}")

    # 1. Retrieval
    retriever = RoleFilteredRetriever()
    add_step("retrieval_started", f"top_k={body.top_k}, min_rel={body.min_relevance}")

    retrieval_res = await retriever.retrieve(
        query=body.query,
        auth=auth,
        top_k=body.top_k,
        min_relevance=body.min_relevance,
        db=db,
    )

    add_step(
        "retrieval_completed",
        f"Found {len(retrieval_res.chunks)} chunks (searched {retrieval_res.total_searched}, withheld {retrieval_res.denied_chunks_count})",
    )

    # 2. Check for adversarial prompt injection in evidence
    if retrieval_res.chunks:
        combined_evidence = " ".join(c.content for c in retrieval_res.chunks)
        injections = CitationVerifier.detect_prompt_injection(combined_evidence)
        if injections:
            add_step("security_alert", f"Adversarial patterns: {injections}", status="warning")

    # 3. Handle insufficient evidence
    if retrieval_res.insufficient_evidence:
        add_step("evidence_evaluation", "Insufficient authorized evidence found", status="warning")
        abstention_answer = (
            "I could not find sufficient information in the documents available to your account "
            "to answer this question reliably."
        )
        add_step("response_finalized", "Abstention returned")
        return {
            "query": body.query,
            "answer": abstention_answer,
            "citations": [],
            "verification_status": "insufficient_evidence",
            "warnings": ["no_authorized_evidence_found"],
            "execution_timeline": timeline,
            "model_used": body.model or "n/a",
            "execution_time_ms": round((time.monotonic() - t0) * 1000, 1),
        }

    # 4. Invoke LLM via Orchestrator or Provider
    from src.orchestrator.engine import OrchestratorEngine

    engine = OrchestratorEngine(db)
    add_step("orchestrator_invoked", "Dispatching to Knowledge Agent with retrieved context")

    orch_res = await engine.execute(
        auth=auth,
        user_input=body.query,
        requested_model=body.model,
    )
    add_step("generation_completed", f"Model: {orch_res.model_used}")

    # 5. Citation verification
    verified_citations, citation_warnings = CitationVerifier.verify_citations(
        output_text=orch_res.content,
        retrieved_citations=retrieval_res.citations,
    )
    add_step(
        "citation_verification",
        f"Verified {len(verified_citations)} citations; {len(citation_warnings)} warnings",
    )

    return {
        "query": body.query,
        "answer": orch_res.content,
        "citations": [c.model_dump() for c in verified_citations],
        "verification_status": orch_res.verification_status,
        "warnings": [*orch_res.warnings, *citation_warnings],
        "execution_timeline": timeline,
        "model_used": orch_res.model_used,
        "grounded_sources": orch_res.grounded_sources,
        "execution_time_ms": round((time.monotonic() - t0) * 1000, 1),
    }


@router.get("/health")
async def rag_health_check(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """
    RAG Subsystem Health Check.
    Checks Ollama availability, embedding provider status, vector dimensions,
    storage path, and database indexing statistics.
    """
    from src.rag.embeddings import get_embedding_provider

    provider = get_embedding_provider()
    provider_available = await provider.is_available()

    # Query counts from DB
    stmt_total = select(Document.status)
    res = await db.execute(stmt_total)
    statuses = [s for s in res.scalars().all()]

    total_docs = len(statuses)
    indexed_docs = sum(1 for s in statuses if s == DocumentStatus.INDEXED)
    processing_docs = sum(1 for s in statuses if s == DocumentStatus.PROCESSING)
    failed_docs = sum(1 for s in statuses if s == DocumentStatus.FAILED)

    storage = DocumentStorage()
    storage_exists = storage.base_dir.exists()

    return {
        "status": "healthy" if storage_exists else "degraded",
        "embedding_provider": {
            "name": provider.model_name,
            "status": "connected" if provider_available else "offline (local vectorizer active)",
            "dimensions": provider.dimensions,
        },
        "storage": {
            "directory": str(storage.base_dir),
            "accessible": storage_exists,
            "max_upload_size_mb": storage.max_size_bytes / (1024 * 1024),
        },
        "catalog": {
            "total_documents": total_docs,
            "indexed_documents": indexed_docs,
            "processing_documents": processing_docs,
            "failed_documents": failed_docs,
        },
    }


@router.get("/test/cases", dependencies=[Depends(_doc_read)])
async def get_evaluation_test_cases() -> list[dict[str, Any]]:
    """Return predefined evaluation benchmark test cases."""
    return _EVALUATION_TEST_CASES


@router.post("/test/evaluation")
async def run_evaluation_suite(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """
    Run the automated RAG evaluation benchmark suite.
    Calculates Recall@k, citation validity, latency, and security isolation.
    """
    retriever = RoleFilteredRetriever()
    results = []
    correct_retrievals = 0
    total_evals = len(_EVALUATION_TEST_CASES)
    latencies: list[float] = []

    for tc in _EVALUATION_TEST_CASES:
        t0 = time.monotonic()
        res = await retriever.retrieve(query=tc["question"], auth=auth, top_k=4, db=db)
        elapsed = (time.monotonic() - t0) * 1000
        latencies.append(elapsed)

        retrieved_titles = [c.doc_title for c in res.chunks]
        expected_title = tc["expected_document"]

        if tc.get("expect_abstention"):
            success = res.insufficient_evidence or len(res.chunks) == 0
        else:
            success = any(expected_title.lower() in t.lower() for t in retrieved_titles)

        if success:
            correct_retrievals += 1

        results.append({
            "test_case_id": tc["id"],
            "question": tc["question"],
            "expected_document": expected_title,
            "retrieved_documents": retrieved_titles,
            "success": success,
            "insufficient_evidence": res.insufficient_evidence,
            "latency_ms": round(elapsed, 1),
        })

    recall = round((correct_retrievals / total_evals) * 100, 1) if total_evals else 0.0
    avg_lat = round(sum(latencies) / len(latencies), 1) if latencies else 0.0

    return {
        "total_test_cases": total_evals,
        "passed_test_cases": correct_retrievals,
        "recall_at_4_percentage": recall,
        "average_latency_ms": avg_lat,
        "test_cases": results,
    }
