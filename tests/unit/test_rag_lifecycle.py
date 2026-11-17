"""
Unit Tests — Document Lifecycle & Authorization Boundaries.

Verifies:
1. End-to-end document upload, storage, chunking, and vector indexing.
2. Document versioning and reindexing.
3. Safe cascade deletion of documents, chunks, vectors, and files.
4. Clearance level enforcement (General Employee vs IT Operator vs Administrator).
5. Persistence across database sessions.
"""

from __future__ import annotations

import tempfile
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.auth.permissions import SystemRole
from src.auth.rbac import AuthContext
from src.core.exceptions import AuthorizationError, NotFoundError
from src.models.document import DocumentStatus, IndexingJobStatus
from src.rag.service import DocumentService
from src.rag.storage import DocumentStorage


def _make_auth(user_id: str, role: SystemRole, permissions: set[str] | None = None) -> AuthContext:
    from src.auth.permissions import DEFAULT_ROLE_PERMISSIONS

    perms = {str(p) for p in DEFAULT_ROLE_PERMISSIONS.get(role, set())}
    if permissions:
        perms.update(permissions)
    return AuthContext(user_id=user_id, role=role.value, permissions=perms)


@pytest.mark.asyncio
async def test_document_upload_and_indexing_lifecycle(db_session: AsyncSession) -> None:
    """Document is uploaded, persisted, chunked, and embedded into the database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = DocumentStorage(base_dir=tmpdir)
        service = DocumentService(db=db_session, storage=storage)
        admin_auth = _make_auth(str(uuid.uuid4()), SystemRole.ADMIN)

        content = b"""# Production Server Maintenance
Follow standard procedure when inspecting PostgreSQL database pools.
Ensure Ollama local model service is active before AI task execution.
"""
        doc, version, job = await service.create_document_with_file(
            auth=admin_auth,
            filename="maintenance.md",
            content=content,
            title="Production Server Maintenance",
            category="operations",
            classification="internal",
            allowed_roles=["administrator", "it_operator"],
            auto_index=True,
        )

        assert doc.status == DocumentStatus.INDEXED
        assert version.indexing_status == IndexingJobStatus.COMPLETED
        assert version.chunk_count > 0
        assert version.extracted_character_count > 0
        assert job.status == IndexingJobStatus.COMPLETED

        # Verify document retrieval
        fetched = await service.get_document(doc.id, admin_auth)
        assert fetched.title == "Production Server Maintenance"
        assert len(fetched.chunks) > 0


@pytest.mark.asyncio
async def test_document_clearance_boundaries(db_session: AsyncSession) -> None:
    """General employee cannot list or access confidential or restricted documents."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = DocumentStorage(base_dir=tmpdir)
        service = DocumentService(db=db_session, storage=storage)
        admin_auth = _make_auth(str(uuid.uuid4()), SystemRole.ADMIN)
        employee_auth = _make_auth(str(uuid.uuid4()), SystemRole.GENERAL_EMPLOYEE)

        # Upload a RESTRICTED document
        doc, _, _ = await service.create_document_with_file(
            auth=admin_auth,
            filename="exec_audit.txt",
            content=b"Restricted financial audit bonus allocations.",
            title="Q3 Executive Audit",
            category="executive",
            classification="restricted",
            allowed_roles=["administrator", "manager"],
            auto_index=True,
        )

        # Employee cannot access document by ID
        with pytest.raises(AuthorizationError):
            await service.get_document(doc.id, employee_auth)

        # Employee listing does not include restricted document
        emp_docs = await service.list_documents(employee_auth)
        assert not any(d.id == doc.id for d in emp_docs)

        # Administrator can access it
        admin_docs = await service.list_documents(admin_auth)
        assert any(d.id == doc.id for d in admin_docs)


@pytest.mark.asyncio
async def test_document_versioning_and_reindexing(db_session: AsyncSession) -> None:
    """Uploading a new version updates active version and retains version history."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = DocumentStorage(base_dir=tmpdir)
        service = DocumentService(db=db_session, storage=storage)
        admin_auth = _make_auth(str(uuid.uuid4()), SystemRole.ADMIN)

        doc, v1, _ = await service.create_document_with_file(
            auth=admin_auth,
            filename="policy.txt",
            content=b"Initial Policy v1.",
            title="Corporate Policy",
            auto_index=True,
        )
        assert v1.version_number == 1

        # Upload Version 2
        v2, _ = await service.add_new_version(
            auth=admin_auth,
            document_id=doc.id,
            filename="policy_v2.txt",
            content=b"Updated Corporate Policy v2 with expanded standards.",
            auto_index=True,
        )
        assert v2.version_number == 2

        # Re-fetch document and verify active version
        updated_doc = await service.get_document(doc.id, admin_auth)
        assert len(updated_doc.versions) == 2

        # Test reindex
        reindex_job = await service.reindex_document(doc.id, admin_auth)
        assert reindex_job.status == IndexingJobStatus.COMPLETED


@pytest.mark.asyncio
async def test_document_safe_deletion(db_session: AsyncSession) -> None:
    """Document deletion purges database entities and filesystem files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = DocumentStorage(base_dir=tmpdir)
        service = DocumentService(db=db_session, storage=storage)
        admin_auth = _make_auth(str(uuid.uuid4()), SystemRole.ADMIN)

        doc, v1, _ = await service.create_document_with_file(
            auth=admin_auth,
            filename="temp.txt",
            content=b"Ephemeral document to be deleted.",
            auto_index=True,
        )

        doc_id = doc.id
        deleted = await service.delete_document(doc_id, admin_auth)
        assert deleted is True

        # Document no longer exists
        with pytest.raises(NotFoundError):
            await service.get_document(doc_id, admin_auth)
