"""
ServerGen AI — Enterprise Document Lifecycle Management Service.

Coordinates document uploads, durable storage, versioning, indexing jobs,
permission enforcement, safe cascade deletion, and audit logging.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.schemas import DataSensitivity
from src.auth.permissions import PermissionCode
from src.auth.rbac import AuthContext, AuthorizationService
from src.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from src.models.document import (
    Document,
    DocumentStatus,
    DocumentVersion,
    IndexingJob,
    IndexingJobStatus,
)
from src.rag.indexer import DocumentIndexer
from src.rag.storage import DocumentStorage
from src.services.audit_service import AuditEventType, AuditService

logger = logging.getLogger("servergen.rag.service")

_ROLE_MAX_CLEARANCE: dict[str, DataSensitivity] = {
    "administrator": DataSensitivity.RESTRICTED,
    "it_operator": DataSensitivity.CONFIDENTIAL,
    "security_analyst": DataSensitivity.CONFIDENTIAL,
    "manager": DataSensitivity.RESTRICTED,
    "general_employee": DataSensitivity.INTERNAL,
}

_SENSITIVITY_ORDER: dict[DataSensitivity, int] = {
    DataSensitivity.PUBLIC: 0,
    DataSensitivity.INTERNAL: 1,
    DataSensitivity.CONFIDENTIAL: 2,
    DataSensitivity.RESTRICTED: 3,
}


class DocumentService:
    """
    High-level lifecycle manager for knowledge documents.
    """

    def __init__(self, db: AsyncSession, storage: DocumentStorage | None = None) -> None:
        self.db = db
        self.storage = storage or DocumentStorage()
        self.audit = AuditService(db)
        self.indexer = DocumentIndexer(db, self.storage)

    def check_user_can_access_doc(
        self, doc: Document, auth: AuthContext, require_write: bool = False
    ) -> bool:
        """Evaluate if user's role and clearance permit access to the document."""
        user_role = auth.role.lower()
        if user_role == "administrator":
            return True

        # Role Vault boundary check:
        # A document in vault 'all' is accessible by all roles (subject to clearance).
        # A document in a role vault (e.g. 'manager', 'it_operator') is strictly isolated
        # and only accessible to users with that exact role.
        doc_vault = (getattr(doc, "vault_scope", "all") or "all").lower()
        if doc_vault != "all" and doc_vault != user_role:
            return False

        # Clearance check
        user_max_sens = _ROLE_MAX_CLEARANCE.get(user_role, DataSensitivity.INTERNAL)
        doc_sens = DataSensitivity(doc.classification.lower())
        if _SENSITIVITY_ORDER[doc_sens] > _SENSITIVITY_ORDER[user_max_sens]:
            return False

        # Role list check
        doc_roles = [r.lower() for r in (doc.allowed_roles or [])]
        is_allowed_role = not doc_roles or user_role in doc_roles
        is_owner = doc.owner_id is not None and str(doc.owner_id) == auth.user_id

        if not (is_allowed_role or is_owner):
            return False

        if require_write:
            has_write_perm = auth.has_any_permission(
                PermissionCode.DOCUMENT_WRITE,
                PermissionCode.DOCUMENT_UPLOAD,
                PermissionCode.DOCUMENT_UPDATE,
            )
            allowed_mgmt_roles = {"administrator", "manager", "it_operator"}
            return bool(
                has_write_perm and (is_owner or user_role in allowed_mgmt_roles)
            )

        return True

    async def create_document_with_file(
        self,
        auth: AuthContext,
        filename: str,
        content: bytes,
        title: str | None = None,
        category: str = "general",
        classification: str = "internal",
        vault_scope: str = "all",
        allowed_roles: list[str] | None = None,
        department: str | None = None,
        description: str = "",
        auto_index: bool = True,
    ) -> tuple[Document, DocumentVersion, IndexingJob]:
        """
        Upload a new document, durably persist the file, create version 1,
        and enqueue or run background indexing.
        """
        # Validate permissions
        AuthorizationService(auth).require_any_permission(
            PermissionCode.DOCUMENT_WRITE, PermissionCode.DOCUMENT_UPLOAD
        )

        user_role = auth.role.lower()
        target_vault = (vault_scope or "all").strip().lower()

        # Validate target vault permissions:
        # Non-admins cannot upload to arbitrary role vaults (only 'all' or their own role)
        if user_role != "administrator" and target_vault != "all" and target_vault != user_role:
            raise AuthorizationError(
                f"Role '{auth.role}' cannot upload into '{target_vault}' vault"
            )

        # Validate classification
        clean_class = classification.strip().lower()
        valid_classes = [s.value for s in DataSensitivity]
        if clean_class not in valid_classes:
            err = f"Invalid classification '{classification}'. Allowed: {valid_classes}"
            raise ValidationError(err)

        # Check user clearance cannot create documents beyond their own clearance
        user_max = _ROLE_MAX_CLEARANCE.get(user_role, DataSensitivity.INTERNAL)
        if _SENSITIVITY_ORDER[DataSensitivity(clean_class)] > _SENSITIVITY_ORDER[user_max]:
            raise AuthorizationError(
                f"Your role ({auth.role}) cannot classify documents as {clean_class.upper()}"
            )

        doc_id = uuid.uuid4()
        doc_title = title.strip() if title and title.strip() else filename.rsplit(".", 1)[0]

        # Default allowed roles based on vault scope
        if allowed_roles:
            roles_assigned = [r.lower() for r in allowed_roles]
        elif target_vault == "all":
            roles_assigned = [
                "administrator", "manager", "it_operator", "security_analyst", "general_employee"
            ]
        else:
            roles_assigned = ["administrator", target_vault]

        # 1. Save original file durably in role-scoped vault
        stored_info = self.storage.save_file(
            document_id=doc_id,
            version_number=1,
            filename=filename,
            content=content,
            vault_scope=target_vault,
        )

        owner_uuid = None
        if auth.user_id:
            try:
                owner_uuid = uuid.UUID(auth.user_id)
            except (ValueError, AttributeError):
                owner_uuid = None

        # 2. Create Document entity
        doc = Document(
            id=doc_id,
            title=doc_title,
            description=description,
            category=category.lower(),
            classification=clean_class,
            vault_scope=target_vault,
            owner_id=owner_uuid,
            department=department,
            allowed_roles=roles_assigned,
            status=DocumentStatus.PROCESSING,
        )
        self.db.add(doc)
        await self.db.flush()

        # 3. Create DocumentVersion entity
        version = DocumentVersion(
            id=uuid.uuid4(),
            document_id=doc.id,
            version_number=1,
            original_filename=stored_info.filename,
            storage_path=stored_info.relative_path,
            mime_type=stored_info.mime_type,
            file_size=stored_info.file_size,
            checksum_sha256=stored_info.checksum_sha256,
            indexing_status=IndexingJobStatus.QUEUED,
        )
        self.db.add(version)
        await self.db.flush()

        doc.active_version_id = version.id

        # 4. Create IndexingJob entity
        job = IndexingJob(
            id=uuid.uuid4(),
            document_id=doc.id,
            version_id=version.id,
            status=IndexingJobStatus.QUEUED,
            configuration={"chunk_size": 500, "overlap": 80},
        )
        self.db.add(job)
        await self.db.commit()

        await self.audit.record(
            event_type=AuditEventType.DOCUMENT_UPLOAD,
            action="document_upload",
            request_id=str(doc.id),
            user_id=auth.user_id,
            role=auth.role,
            decision="allow",
            resource=f"document/{doc.id}",
            metadata={
                "title": doc.title,
                "filename": filename,
                "size_bytes": stored_info.file_size,
                "classification": clean_class,
                "checksum": stored_info.checksum_sha256,
            },
        )

        # 5. Execute indexing if requested
        if auto_index:
            await self.indexer.run_indexing_job(job.id)
            await self.db.refresh(doc)
            await self.db.refresh(version)
            await self.db.refresh(job)

        return doc, version, job

    async def add_new_version(
        self,
        auth: AuthContext,
        document_id: uuid.UUID,
        filename: str,
        content: bytes,
        auto_index: bool = True,
    ) -> tuple[DocumentVersion, IndexingJob]:
        """Upload a new version to an existing document."""
        AuthorizationService(auth).require_any_permission(
            PermissionCode.DOCUMENT_WRITE, PermissionCode.DOCUMENT_UPDATE
        )

        res = await self.db.execute(select(Document).where(Document.id == document_id))
        doc = res.scalar_one_or_none()
        if not doc or doc.is_deleted:
            raise NotFoundError(f"Document {document_id} not found")

        if not self.check_user_can_access_doc(doc, auth, require_write=True):
            raise AuthorizationError(
                "Access denied: insufficient permission to update this document"
            )

        # Find latest version number
        stmt = (
            select(func.max(DocumentVersion.version_number))
            .where(DocumentVersion.document_id == document_id)
        )
        current_max = (await self.db.execute(stmt)).scalar() or 0
        new_version_num = current_max + 1

        doc_vault = (getattr(doc, "vault_scope", "all") or "all").lower()
        stored_info = self.storage.save_file(
            document_id=doc.id,
            version_number=new_version_num,
            filename=filename,
            content=content,
            vault_scope=doc_vault,
        )

        version = DocumentVersion(
            id=uuid.uuid4(),
            document_id=doc.id,
            version_number=new_version_num,
            original_filename=stored_info.filename,
            storage_path=stored_info.relative_path,
            mime_type=stored_info.mime_type,
            file_size=stored_info.file_size,
            checksum_sha256=stored_info.checksum_sha256,
            indexing_status=IndexingJobStatus.QUEUED,
        )
        self.db.add(version)
        doc.versions.append(version)
        await self.db.flush()

        job = IndexingJob(
            id=uuid.uuid4(),
            document_id=doc.id,
            version_id=version.id,
            status=IndexingJobStatus.QUEUED,
        )
        self.db.add(job)
        await self.db.commit()

        await self.audit.record(
            event_type=AuditEventType.DOCUMENT_VERSION_CREATED,
            action="document_version_created",
            request_id=str(version.id),
            user_id=auth.user_id,
            role=auth.role,
            decision="allow",
            resource=f"document/{doc.id}/version/{new_version_num}",
            metadata={"document_id": str(doc.id), "version": new_version_num, "filename": filename},
        )

        if auto_index:
            await self.indexer.run_indexing_job(job.id)
            await self.db.refresh(version)
            await self.db.refresh(job)

        return version, job

    async def list_documents(
        self,
        auth: AuthContext,
        category: str | None = None,
        classification: str | None = None,
        vault_scope: str | None = None,
        search_query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Document]:
        """Retrieve authorized documents accessible to the user."""
        AuthorizationService(auth).require_permission(PermissionCode.DOCUMENT_READ)

        user_role = auth.role.lower()
        user_max_sens = _ROLE_MAX_CLEARANCE.get(user_role, DataSensitivity.INTERNAL)
        max_rank = _SENSITIVITY_ORDER[user_max_sens]

        # Allowed classifications based on clearance
        allowed_classifications = [
            s.value for s, rank in _SENSITIVITY_ORDER.items() if rank <= max_rank
        ]

        stmt = select(Document).where(
            Document.is_deleted.is_(False),
            Document.classification.in_(allowed_classifications),
        )

        # Enforce role-vault scoping
        if vault_scope:
            v_clean = vault_scope.strip().lower()
            if user_role != "administrator" and v_clean != "all" and v_clean != user_role:
                raise AuthorizationError(
                    f"Access denied: role '{auth.role}' cannot view '{v_clean}' vault"
                )
            stmt = stmt.where(Document.vault_scope == v_clean)
        elif user_role != "administrator":
            # Non-admins only see company-wide 'all' and their own role vault
            stmt = stmt.where(Document.vault_scope.in_(["all", user_role]))

        if category:
            stmt = stmt.where(Document.category == category.lower())
        if classification:
            stmt = stmt.where(Document.classification == classification.lower())
        if search_query:
            stmt = stmt.where(Document.title.ilike(f"%{search_query}%"))

        stmt = stmt.order_by(Document.created_at.desc()).limit(limit).offset(offset)
        res = await self.db.execute(stmt)
        docs = res.scalars().all()

        # Filter by role clearance and allowed_roles
        accessible = []
        for d in docs:
            if self.check_user_can_access_doc(d, auth):
                accessible.append(d)

        return accessible

    async def get_document(self, document_id: uuid.UUID, auth: AuthContext) -> Document:
        """Fetch document details with permission check."""
        AuthorizationService(auth).require_permission(PermissionCode.DOCUMENT_READ)

        res = await self.db.execute(
            select(Document).where(Document.id == document_id, Document.is_deleted.is_(False))
        )
        doc = res.scalar_one_or_none()
        if not doc:
            raise NotFoundError(f"Document {document_id} not found")

        if not self.check_user_can_access_doc(doc, auth):
            await self.audit.record(
                event_type=AuditEventType.DOCUMENT_ACCESS_DENIED,
                action="document_access_denied",
                request_id=str(document_id),
                user_id=auth.user_id,
                role=auth.role,
                decision="deny",
                resource=f"document/{document_id}",
            )
            raise AuthorizationError("Access denied to requested document")

        return doc

    async def delete_document(self, document_id: uuid.UUID, auth: AuthContext) -> bool:
        """Safely delete document, database records, and physical storage files."""
        AuthorizationService(auth).require_any_permission(
            PermissionCode.DOCUMENT_DELETE, PermissionCode.ADMIN_MANAGE
        )

        res = await self.db.execute(select(Document).where(Document.id == document_id))
        doc = res.scalar_one_or_none()
        if not doc or doc.is_deleted:
            raise NotFoundError(f"Document {document_id} not found")

        # Admin or owner with delete perm
        if auth.role.lower() != "administrator" and str(doc.owner_id) != auth.user_id:
            raise AuthorizationError(
                "Only the document owner or an Administrator can delete documents"
            )

        # Physical file removal across vaults
        doc_vault = getattr(doc, "vault_scope", None)
        self.storage.delete_document_tree(document_id, vault_scope=doc_vault)

        # Database cascade delete
        await self.db.delete(doc)
        await self.db.commit()

        await self.audit.record(
            event_type=AuditEventType.DOCUMENT_DELETED,
            action="document_deleted",
            request_id=str(document_id),
            user_id=auth.user_id,
            role=auth.role,
            decision="allow",
            resource=f"document/{document_id}",
            metadata={"title": doc.title},
        )
        return True

    async def reindex_document(self, document_id: uuid.UUID, auth: AuthContext) -> IndexingJob:
        """Trigger reindexing for the active version of a document."""
        AuthorizationService(auth).require_any_permission(
            PermissionCode.DOCUMENT_REINDEX,
            PermissionCode.DOCUMENT_WRITE,
            PermissionCode.ADMIN_MANAGE,
        )

        doc = await self.get_document(document_id, auth)
        if not doc.active_version_id:
            raise ValidationError("Document has no active version to reindex")

        job = IndexingJob(
            id=uuid.uuid4(),
            document_id=doc.id,
            version_id=doc.active_version_id,
            status=IndexingJobStatus.QUEUED,
        )
        self.db.add(job)
        await self.db.commit()

        await self.audit.record(
            event_type=AuditEventType.DOCUMENT_REINDEX_REQUESTED,
            action="document_reindex_requested",
            request_id=str(job.id),
            user_id=auth.user_id,
            role=auth.role,
            decision="allow",
            resource=f"document/{doc.id}/reindex",
        )

        await self.indexer.run_indexing_job(job.id)
        await self.db.refresh(job)
        return job
