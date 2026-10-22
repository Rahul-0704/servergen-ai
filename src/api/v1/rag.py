"""
ServerGen AI — RAG Knowledge API Routes.

GET  /api/v1/rag/documents — list accessible organizational knowledge documents
POST /api/v1/rag/documents — register a new organizational document (requires document.write)
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.ai.schemas import DataSensitivity
from src.auth.permissions import PermissionCode
from src.auth.rbac import AuthContext, get_auth_context, require_permission
from src.rag.schemas import DocumentCategory, KnowledgeDocument
from src.rag.store import KnowledgeStore

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])

_doc_read = require_permission(PermissionCode.DOCUMENT_READ)
_doc_write = require_permission(PermissionCode.DOCUMENT_WRITE)


class DocumentCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    content: str = Field(..., min_length=10)
    category: DocumentCategory = DocumentCategory.GENERAL
    classification: DataSensitivity = DataSensitivity.INTERNAL
    allowed_roles: list[str] = Field(default_factory=list)


@router.get("/documents", dependencies=[Depends(_doc_read)])
async def list_documents(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> list[dict[str, Any]]:
    """List organizational documents accessible to the caller's role."""
    store = KnowledgeStore.get_instance()
    user_role = auth.role.lower()

    docs = store.list_documents()
    accessible = []
    for d in docs:
        if not d.allowed_roles or user_role in [r.lower() for r in d.allowed_roles]:
            accessible.append({
                "id": str(d.id),
                "title": d.title,
                "category": d.category.value,
                "classification": d.classification.value,
                "allowed_roles": d.allowed_roles,
                "content_preview": d.content[:160] + "...",
                "created_at": d.created_at.isoformat(),
            })
    return accessible


@router.post("/documents", dependencies=[Depends(_doc_write)])
async def create_document(
    body: DocumentCreateRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> dict[str, Any]:
    """Register a new organizational knowledge document (requires document.write)."""
    store = KnowledgeStore.get_instance()
    doc = KnowledgeDocument(
        title=body.title,
        content=body.content,
        category=body.category,
        classification=body.classification,
        allowed_roles=body.allowed_roles or [auth.role],
    )
    store.add_document(doc)
    return {
        "status": "created",
        "id": str(doc.id),
        "title": doc.title,
        "classification": doc.classification.value,
        "allowed_roles": doc.allowed_roles,
    }
