"""
ServerGen AI — PDF and Presentation Generation API Routes.

Exposes REST endpoints for:
1. POST /api/v1/generate/presentation — Generate 16:9 widescreen PowerPoint deck with local LLM.
2. POST /api/v1/generate/pdf          — Generate publication-ready corporate PDF report.
3. POST /api/v1/generate/from-rag     — Synthesize PDF or presentation directly from RAG documents.
4. GET  /api/v1/generate/download/{id} — Secure binary file download.
5. GET  /api/v1/generate/history      — List previously generated documents and presentations.
"""

from __future__ import annotations

import logging
import mimetypes
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.schemas import DataSensitivity
from src.auth.permissions import PermissionCode
from src.auth.rbac import AuthContext, get_auth_context, require_permission
from src.core.database import get_db
from src.core.exceptions import NotFoundError, ValidationError
from src.rag.retriever import RoleFilteredRetriever
from src.services.audit_service import AuditService
from src.services.docgen_service import (
    DocumentGeneratorService,
    GeneratedFileMeta,
    PresentationDeck,
    ReportDocument,
)

logger = logging.getLogger("servergen.api.generate")

router = APIRouter(prefix="/api/v1/generate", tags=["generation"])

_ai_execute = require_permission(PermissionCode.AI_EXECUTE)
_doc_read = require_permission(PermissionCode.DOCUMENT_READ)


# ── Request Models ──────────────────────────────────────────────────────────


class GeneratePresentationRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=1000, description="Topic or prompt")
    num_slides: int = Field(default=5, ge=3, le=12, description="Slide count (3-12)")
    classification: str = Field(default="INTERNAL", description="Security classification")
    context: str = Field(default="", description="Optional reference background text")
    model: str | None = Field(default=None, description="Optional local model override")


class GeneratePDFRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=1000, description="Topic or title")
    classification: str = Field(default="INTERNAL", description="Security classification")
    context: str = Field(default="", description="Optional reference background text")
    model: str | None = Field(default=None, description="Optional local model override")


class GenerateFromRAGRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000, description="Search query or topic")
    target_format: str = Field(default="pdf", description="'pdf' or 'pptx'")
    num_slides: int = Field(default=5, ge=3, le=12)
    classification: str = Field(default="INTERNAL")
    top_k: int = Field(default=4, ge=1, le=10)


class GenerationResponse(BaseModel):
    success: bool
    message: str
    meta: GeneratedFileMeta
    outline: dict[str, Any] = Field(default_factory=dict)


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.post(
    "/presentation",
    response_model=GenerationResponse,
    dependencies=[Depends(_ai_execute)],
)
async def generate_presentation(
    body: GeneratePresentationRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GenerationResponse:
    """Generate a PowerPoint (PPTX) presentation using local AI model."""
    svc = DocumentGeneratorService()
    try:
        deck, _, meta = await svc.generate_presentation_from_prompt(
            prompt=body.topic,
            num_slides=body.num_slides,
            context=body.context,
            classification=body.classification,
            model=body.model,
        )

        audit = AuditService(db)
        await audit.record(
            event_type="document:generate_pptx",
            action="generate_presentation",
            request_id=str(uuid.uuid4()),
            user_id=auth.user_id,
            role=auth.role,
            resource=meta.filename,
            metadata={
                "title": deck.title,
                "slides": len(deck.slides),
                "file_size": meta.file_size,
            },
        )
        await db.commit()

        return GenerationResponse(
            success=True,
            message=f"Generated {len(deck.slides)}-slide presentation successfully.",
            meta=meta,
            outline=deck.model_dump(),
        )
    except Exception as exc:
        logger.error("Failed to generate presentation: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate presentation: {exc}",
        ) from exc


@router.post(
    "/pdf",
    response_model=GenerationResponse,
    dependencies=[Depends(_ai_execute)],
)
async def generate_pdf(
    body: GeneratePDFRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GenerationResponse:
    """Generate an executive publication-ready PDF report using local AI."""
    svc = DocumentGeneratorService()
    try:
        doc_data, _, meta = await svc.generate_pdf_from_prompt(
            prompt=body.topic,
            classification=body.classification,
            context=body.context,
            model=body.model,
        )

        audit = AuditService(db)
        await audit.record(
            event_type="document:generate_pdf",
            action="generate_pdf",
            request_id=str(uuid.uuid4()),
            user_id=auth.user_id,
            role=auth.role,
            resource=meta.filename,
            metadata={
                "title": doc_data.title,
                "sections": len(doc_data.sections),
                "file_size": meta.file_size,
            },
        )
        await db.commit()

        return GenerationResponse(
            success=True,
            message=f"Generated executive PDF report '{doc_data.title}' successfully.",
            meta=meta,
            outline=doc_data.model_dump(),
        )
    except Exception as exc:
        logger.error("Failed to generate PDF: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PDF report: {exc}",
        ) from exc


@router.post(
    "/from-rag",
    response_model=GenerationResponse,
    dependencies=[Depends(_ai_execute)],
)
async def generate_from_rag(
    body: GenerateFromRAGRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GenerationResponse:
    """Retrieve grounded knowledge from RAG and generate a PDF report or presentation."""
    retriever = RoleFilteredRetriever()
    user_sens = DataSensitivity.from_str(body.classification)
    rag_result = await retriever.retrieve(
        db=db,
        query=body.query,
        user_role=auth.role,
        user_id=auth.user_id,
        user_permissions=auth.permissions,
        top_k=body.top_k,
        max_sensitivity=user_sens,
    )

    context_text = rag_result.context_text or ""
    svc = DocumentGeneratorService()

    if body.target_format.lower() in ("pptx", "presentation", "ppt"):
        deck, _, meta = await svc.generate_presentation_from_prompt(
            prompt=body.query,
            num_slides=body.num_slides,
            context=context_text,
            classification=body.classification,
        )
        return GenerationResponse(
            success=True,
            message=f"Grounded presentation generated from {len(rag_result.chunks)} retrieved sources.",
            meta=meta,
            outline=deck.model_dump(),
        )
    else:
        doc_data, _, meta = await svc.generate_pdf_from_prompt(
            prompt=body.query,
            classification=body.classification,
            context=context_text,
        )
        return GenerationResponse(
            success=True,
            message=f"Grounded PDF report generated from {len(rag_result.chunks)} retrieved sources.",
            meta=meta,
            outline=doc_data.model_dump(),
        )


@router.get("/history", response_model=list[GeneratedFileMeta])
async def list_history(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> list[GeneratedFileMeta]:
    """List previously generated PDF and PowerPoint presentations."""
    svc = DocumentGeneratorService()
    return svc.list_generated_files()


@router.get("/download/{file_id_or_name}")
async def download_generated_file(
    file_id_or_name: str,
) -> FileResponse:
    """
    Download a generated PDF or PPTX file.
    Does not require Bearer header so standard browser links/tags can download directly.
    """
    svc = DocumentGeneratorService()
    file_path = svc.get_file_path(file_id_or_name)
    if not file_path or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generated document or presentation file not found.",
        )

    ext = file_path.suffix.lower()
    media_type = (
        "application/pdf"
        if ext == ".pdf"
        else "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=file_path.name,
        headers={"Content-Disposition": f'attachment; filename="{file_path.name}"'},
    )
