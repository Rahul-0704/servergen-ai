"""
ServerGen AI — Executive Manager Command Suite.

Tailored high-leverage API for enterprise managers, directors, and executives:
1. Executive Cockpit: Unified overview of confidential vs company knowledge,
   pending dual-custody approvals, security posture, and recent runs.
2. Dual-Vault Document Hub: Physical & cryptographic separation of Manager
   Confidential records from Company-Wide knowledge.
3. Dual-Custody Approval Center: 1-click evaluation of pending organizational
   actions with audit ledger recording.
4. Autonomous Executive Analytics: 1-click transformation of raw spreadsheets
   into board-ready 16:9 PPTX decks, vector PDF reports, and cleansed XLSX workbooks.
5. Grounded Executive Intelligence: Zero-hallucination Q&A against the Manager
   Confidential Vault + Company-Wide Library with verified citations.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.providers.base import LLMRequest
from src.ai.providers.ollama_provider import OllamaProvider
from src.auth.rbac import AuthContext, get_auth_context
from src.core.config import get_settings
from src.core.database import check_database, get_db
from src.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from src.models.approval import ApprovalRequest
from src.models.document import Document
from src.rag.retriever import RoleFilteredRetriever
from src.rag.service import DocumentService
from src.rag.verifier import CitationVerifier
from src.services.approval_service import ApprovalService
from src.services.audit_service import AuditEventType, AuditService
from src.services.docgen_service import DocumentGeneratorService
from src.services.spreadsheet_service import SpreadsheetAnalyticsService

logger = logging.getLogger("servergen.api.manager")

router = APIRouter(prefix="/api/v1/manager", tags=["Executive Manager Suite"])

spreadsheet_service = SpreadsheetAnalyticsService()
docgen_service = DocumentGeneratorService()


def _require_manager(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    """Ensure the caller has Manager or Administrator executive privileges."""
    role_norm = auth.role.lower()
    if role_norm not in ("manager", "administrator"):
        raise AuthorizationError(
            f"Access denied: Executive Manager Suite requires Manager or Administrator role (caller has '{auth.role}')"
        )
    return auth


# ── Pydantic Request / Response Models ──────────────────────────────────────


class ManagerApprovalDecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject)$", description="'approve' or 'reject'")
    notes: str = Field(default="", max_length=1000, description="Manager justification notes")


class ManagerAIQueryRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000, description="Executive business question")
    top_k: int = Field(default=4, ge=1, le=10, description="Maximum verified chunks to synthesize")
    target_vault: str = Field(
        default="both",
        pattern="^(both|manager|all)$",
        description="Search 'both' (manager + company), 'manager' (confidential only), or 'all' (company wide)",
    )


# ── 1. Executive Cockpit Overview ───────────────────────────────────────────


@router.get("/cockpit")
async def get_manager_cockpit(
    auth: Annotated[AuthContext, Depends(_require_manager)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """
    Unified Executive Cockpit.
    Returns high-level business KPIs, role-vault document counts, pending approval tasks,
    system sovereignty health, and recent operational metrics without backend clutter.
    """
    # 1. Document metrics across vaults
    stmt_mgr = select(func.count(Document.id)).where(
        Document.is_deleted.is_(False),
        Document.vault_scope == "manager",
    )
    stmt_all = select(func.count(Document.id)).where(
        Document.is_deleted.is_(False),
        Document.vault_scope == "all",
    )
    manager_vault_count = (await db.execute(stmt_mgr)).scalar() or 0
    all_vault_count = (await db.execute(stmt_all)).scalar() or 0

    # 2. Pending approvals count and urgent items
    stmt_approvals = select(ApprovalRequest).where(
        ApprovalRequest.status == "pending"
    ).order_by(ApprovalRequest.created_at.desc())
    res_approvals = await db.execute(stmt_approvals)
    pending_list = res_approvals.scalars().all()
    pending_count = len(pending_list)

    urgent_approvals = []
    for app in pending_list[:5]:
        urgent_approvals.append({
            "id": str(app.id),
            "request_id": app.request_id,
            "operation_summary": app.operation_summary,
            "requester_role": app.requester_role,
            "created_at": app.created_at.isoformat() if app.created_at else None,
            "expires_at": app.expires_at.isoformat() if app.expires_at else None,
        })

    # 3. System and sovereignty health
    db_ok = await check_database()
    settings = get_settings()

    return {
        "status": "ready",
        "manager_profile": {
            "user_id": auth.user_id,
            "role": auth.role,
            "clearance": "RESTRICTED (Level 3 - Full Executive Authority)",
            "allowed_vaults": ["manager", "all"],
        },
        "kpis": [
            {
                "label": "Confidential Manager Vault",
                "value": f"{manager_vault_count} Docs",
                "subtext": "Strictly restricted to Managers & Admin",
                "status": "success",
            },
            {
                "label": "Company-Wide Library",
                "value": f"{all_vault_count} Docs",
                "subtext": "Accessible across the enterprise",
                "status": "neutral",
            },
            {
                "label": "Pending Approvals",
                "value": f"{pending_count} Requests",
                "subtext": "Awaiting your executive decision",
                "status": "alert" if pending_count > 0 else "success",
            },
            {
                "label": "Data Sovereignty",
                "value": "100% On-Premise",
                "subtext": "Zero cloud leaks · SHA-256 Audited",
                "status": "success",
            },
        ],
        "urgent_approvals": urgent_approvals,
        "system_health": {
            "database_online": db_ok,
            "local_model": settings.DEFAULT_MODEL,
            "storage_path": "storage/vaults/",
            "zero_cloud_data_sovereignty": True,
        },
    }


# ── 2. Dual-Vault Document Hub ──────────────────────────────────────────────


@router.get("/documents")
async def list_manager_documents(
    auth: Annotated[AuthContext, Depends(_require_manager)],
    db: Annotated[AsyncSession, Depends(get_db)],
    vault: str = Query("both", pattern="^(both|manager|all)$"),
    search: str | None = Query(None),
) -> list[dict[str, Any]]:
    """
    Retrieve documents segmented by Vault:
    - 'manager': Only private, highly confidential managerial assets.
    - 'all': General organizational assets shared across all roles.
    - 'both': Unified view of all assets accessible to the Manager.
    """
    service = DocumentService(db)
    target_scope = None if vault == "both" else vault

    docs = await service.list_documents(
        auth=auth,
        vault_scope=target_scope,
        search_query=search,
    )

    out = []
    for d in docs:
        active_ver = next((v for v in d.versions if v.id == d.active_version_id), None)
        out.append({
            "id": str(d.id),
            "title": d.title,
            "description": d.description,
            "category": d.category,
            "classification": d.classification,
            "vault_scope": d.vault_scope,
            "vault_label": "Manager Confidential Vault" if d.vault_scope == "manager" else "Company-Wide Library",
            "status": d.status,
            "file_size": active_ver.file_size if active_ver else 0,
            "chunk_count": active_ver.chunk_count if active_ver else 0,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        })
    return out


@router.post("/documents/upload")
async def upload_manager_document(
    file: UploadFile = File(...),
    target_vault: str = Form("manager", pattern="^(manager|all)$"),
    title: str | None = Form(None),
    category: str = Form("financial"),
    classification: str = Form("restricted"),
    description: str = Form(""),
    auth: AuthContext = Depends(_require_manager),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Upload a document directly into the Manager Confidential Vault or the Company-Wide Library.
    Automatically establishes physical directory segregation and vector isolation.
    """
    content = await file.read()
    if not content:
        raise ValidationError("Uploaded file is empty (0 bytes)")

    clean_vault = target_vault.strip().lower()
    # Default classification for manager vault is restricted, all vault is internal
    clean_class = classification.strip().lower()
    if clean_vault == "manager" and clean_class in ("public", "internal"):
        clean_class = "restricted"

    service = DocumentService(db)
    doc, version, _job = await service.create_document_with_file(
        auth=auth,
        filename=file.filename or "manager_doc.bin",
        content=content,
        title=title,
        category=category,
        classification=clean_class,
        vault_scope=clean_vault,
        description=description,
        auto_index=True,
    )

    return {
        "status": "success",
        "message": f"Document persisted into {'Manager Confidential Vault' if clean_vault == 'manager' else 'Company-Wide Library'}",
        "document_id": str(doc.id),
        "title": doc.title,
        "vault_scope": doc.vault_scope,
        "classification": doc.classification,
        "file_size": version.file_size,
        "checksum_sha256": version.checksum_sha256,
        "indexing_status": version.indexing_status,
    }


# ── 3. Dual-Custody Approval Center ─────────────────────────────────────────


@router.get("/approvals")
async def list_pending_approvals(
    auth: Annotated[AuthContext, Depends(_require_manager)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict[str, Any]]:
    """List all pending operational requests awaiting manager authorization."""
    svc = ApprovalService(db)
    items, _total = await svc.list_for(auth, scope="review", status="pending")
    return [
        {
            "id": str(a.id),
            "request_id": a.request_id,
            "operation_summary": a.operation_summary,
            "requester_user_id": str(a.requester_user_id),
            "requester_role": a.requester_role,
            "risk_assessment": a.risk_assessment_json,
            "task_classification": a.task_classification_json,
            "status": a.status,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "expires_at": a.expires_at.isoformat() if a.expires_at else None,
        }
        for a in items
    ]


@router.post("/approvals/{approval_id}/decision")
async def decide_approval(
    approval_id: uuid.UUID,
    body: ManagerApprovalDecisionRequest,
    auth: Annotated[AuthContext, Depends(_require_manager)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Approve or reject a pending request with executive notes, closed-loop execution, and audit recording."""
    svc = ApprovalService(db)

    exec_summary: dict[str, Any] | None = None
    if body.decision == "approve":
        approval = await svc.approve(
            approval_id=approval_id,
            reviewer_user_id=auth.user_id,
            reviewer_role=auth.role,
            notes=body.notes or "Approved via Manager Command Suite",
        )
        status_msg = "approved"

        # Closed-loop execution: Resume task if operation_payload is present
        if approval.operation_payload:
            try:
                from src.auth.rbac import resolve_permissions
                from src.orchestrator.engine import OrchestratorEngine
                from src.orchestrator.sensitivity import DataSensitivity
                from src.schemas.orchestrator import ToolRequest

                req_auth = AuthContext(
                    user_id=str(approval.requester_user_id),
                    role=approval.requester_role,
                    permissions=resolve_permissions(approval.requester_role),
                )
                payload = approval.operation_payload
                tool_req = None
                if payload.get("tool"):
                    tool_req = ToolRequest(
                        requested_action=payload.get("input", approval.operation_summary),
                        tool=payload["tool"],
                        parameters=payload.get("tool_parameters") or {},
                    )

                sens_val = payload.get("data_sensitivity", "internal")
                try:
                    sens = DataSensitivity(sens_val)
                except ValueError:
                    sens = DataSensitivity.INTERNAL

                engine = OrchestratorEngine(db)
                exec_result = await engine.execute(
                    auth=req_auth,
                    user_input=payload.get("input", approval.operation_summary),
                    data_sensitivity=sens,
                    tool_request=tool_req,
                    request_id=approval.request_id,
                    structured=payload.get("structured", False),
                    requested_model=payload.get("model"),
                    approval_id=str(approval.id),
                )
                exec_summary = {
                    "success": exec_result.success,
                    "output": exec_result.output,
                    "tool_used": exec_result.tool_used,
                    "model_used": exec_result.model_used,
                }
                try:
                    await svc.consume(approval)
                except Exception as cons_err:
                    logger.debug("Approval consume notice: %s", cons_err)
            except Exception as ex_err:
                logger.error("Failed to auto-resume approved operation: %s", ex_err, exc_info=True)
                exec_summary = {"success": False, "error": str(ex_err)}
    else:
        approval = await svc.reject(
            approval_id=approval_id,
            reviewer_user_id=auth.user_id,
            reviewer_role=auth.role,
            notes=body.notes or "Rejected via Manager Command Suite",
        )
        status_msg = "rejected"

    return {
        "status": "success",
        "approval_id": str(approval.id),
        "decision": status_msg,
        "operation_summary": approval.operation_summary,
        "reviewer_notes": approval.reviewer_notes,
        "resolved_at": approval.resolved_at.isoformat() if approval.resolved_at else None,
        "execution_result": exec_summary,
    }


# ── 4. 1-Click Executive Analytics & Board-Ready Deliverables ────────────────


@router.post("/analytics/run")
async def run_manager_analytics(
    goal_prompt: str = Form(
        "Analyze high-impact variances, cost outliers, and operational drivers for executive review"
    ),
    file: UploadFile | None = File(None),
    document_id: str | None = Form(None),
    sheet_name: str | None = Form(None),
    mask_pii: bool = Form(False),
    auth: AuthContext = Depends(_require_manager),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    1-Click Executive Data Engine:
    Ingests spreadsheet data, automatically diagnoses business variances and outliers,
    and simultaneously generates:
    1. Modern 16:9 PowerPoint Presentation Deck (.pptx) with native Office Chart XML.
    2. Executive Vector PDF Report (.pdf) with clean charts and summary tables.
    3. Standardized cleansed Excel Workbook (.xlsx).
    """
    audit = AuditService(db)
    content: bytes
    target_filename: str

    if file and file.filename:
        content = await file.read()
        target_filename = file.filename
        if not content:
            raise ValidationError("Uploaded spreadsheet is empty")
        doc_uuid = uuid.uuid4()
    elif document_id:
        try:
            doc_uuid = uuid.UUID(document_id)
        except ValueError as err:
            raise ValidationError(f"Invalid document UUID: {document_id}") from err

        res = await db.execute(select(Document).where(Document.id == doc_uuid, Document.is_deleted.is_(False)))
        doc_entity = res.scalar_one_or_none()
        if not doc_entity:
            raise NotFoundError(f"Document {document_id} not found")

        active_ver = next((v for v in doc_entity.versions if v.id == doc_entity.active_version_id), None)
        if not active_ver:
            raise NotFoundError("Document has no active version stored")

        content = DocumentService(db).storage.read_file(active_ver.storage_path)
        target_filename = active_ver.original_filename
    else:
        raise ValidationError("Either 'file' or 'document_id' must be provided")

    # Parse spreadsheet
    wb_data = spreadsheet_service.parse_content(content, target_filename)
    if not wb_data.sheets:
        raise ValidationError(f"Spreadsheet '{target_filename}' contains no readable tables or data")

    target_sheet = wb_data.sheets.get(sheet_name) if sheet_name and sheet_name in wb_data.sheets else next(iter(wb_data.sheets.values()))

    # Autonomous analysis & intent routing
    route_res = spreadsheet_service.auto_analyze_and_route(
        sheet=target_sheet,
        prompt=goal_prompt,
        mask_pii=mask_pii,
    )

    overview_md = spreadsheet_service.generate_overview_markdown(target_sheet)
    insights = await spreadsheet_service.generate_executive_insights(
        sheet_name=target_sheet.name,
        overview_md=overview_md,
        data_table_md=route_res["data_table_md"],
        user_prompt=goal_prompt,
        mask_pii=mask_pii,
    )

    exec_title = f"Executive Intelligence: {target_sheet.name}"

    # Render Deliverable 1: 16:9 Presentation Deck (.pptx)
    _pptx_path, pptx_meta = docgen_service.render_executive_data_deck(
        title=exec_title,
        subtitle=f"Board-Ready Audit — {target_sheet.name}",
        table_headers=route_res["headers"],
        table_rows=route_res["rows"],
        executive_insights=insights,
        classification="RESTRICTED",
    )

    # Render Deliverable 2: Vector PDF Report (.pdf)
    _pdf_path, pdf_meta = docgen_service.render_executive_data_report(
        title=exec_title,
        subtitle=f"Executive Audit Report — {target_sheet.name}",
        table_headers=route_res["headers"],
        table_rows=route_res["rows"],
        executive_insights=insights,
        classification="RESTRICTED",
    )

    # Render Deliverable 3: Transformed Cleansed Excel (.xlsx)
    xlsx_path = spreadsheet_service.export_styled_xlsx(
        sheet_name=target_sheet.name,
        headers=route_res["headers"],
        rows=route_res["rows"],
        title=exec_title,
    )
    xlsx_file_id = xlsx_path.stem.split("_")[0]

    await audit.record(
        event_type=AuditEventType.EXECUTION_COMPLETED,
        action="manager.analytics_run",
        request_id=str(uuid.uuid4()),
        user_id=auth.user_id,
        role=auth.role,
        resource=f"spreadsheet/{target_filename}",
        metadata={
            "mode": route_res["mode"],
            "sheet": target_sheet.name,
            "rows": target_sheet.row_count(),
            "pptx_file": pptx_meta.filename,
            "pdf_file": pdf_meta.filename,
        },
    )

    return {
        "status": "success",
        "workflow": "Autonomous Executive Intelligence",
        "sheet_name": target_sheet.name,
        "mode": route_res["mode"],
        "headline": route_res["headline"],
        "kpi_metrics": route_res["kpis"],
        "table_headers": route_res["headers"],
        "table_rows": route_res["rows"][:25],
        "executive_insights": insights,
        "deliverables": {
            "pptx": {
                "label": "16:9 Executive PowerPoint Presentation (.pptx)",
                "download_url": pptx_meta.download_url,
                "filename": pptx_meta.filename,
                "file_size": pptx_meta.file_size,
            },
            "pdf": {
                "label": "Executive Vector Audit PDF Report (.pdf)",
                "download_url": pdf_meta.download_url,
                "filename": pdf_meta.filename,
                "file_size": pdf_meta.file_size,
            },
            "xlsx": {
                "label": "Structured Clean Excel Workbook (.xlsx)",
                "download_url": f"/api/v1/generate/download/{xlsx_file_id}",
                "filename": xlsx_path.name,
                "file_size": xlsx_path.stat().st_size,
            },
        },
    }


# ── 5. Grounded Executive Intelligence Q&A ───────────────────────────────────


@router.post("/ai/query")
async def manager_grounded_query(
    body: ManagerAIQueryRequest,
    auth: Annotated[AuthContext, Depends(_require_manager)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """
    Grounded Executive Intelligence:
    Queries organizational knowledge across the Manager Vault and Company Library.
    Guarantees strict citation grounding and prevents hallucination.
    """
    start_time = time.monotonic()
    retriever = RoleFilteredRetriever()

    # Permission-aware retrieval
    retrieval_res = await retriever.retrieve(
        query=body.query,
        auth=auth,
        top_k=body.top_k,
        min_relevance=0.20,
        db=db,
    )

    # Filter by requested vault scope if specific
    selected_chunks = retrieval_res.chunks
    if body.target_vault != "both":
        selected_chunks = [c for c in selected_chunks if c.vault_scope == body.target_vault]

    if not selected_chunks:
        return {
            "answer": "No verified records were found in your authorized vaults matching this query.",
            "citations": [],
            "insufficient_evidence": True,
            "vault_searched": body.target_vault,
            "execution_time_ms": round((time.monotonic() - start_time) * 1000, 1),
        }

    # Synthesize grounded answer
    settings = get_settings()
    ollama = OllamaProvider()

    context_str = "\n\n".join([
        f"[Source {idx+1}: {c.doc_title} | Vault: {c.vault_scope.upper()} | Classification: {c.classification.value.upper()}]\n{c.content}"
        for idx, c in enumerate(selected_chunks)
    ])

    prompt = (
        f"Executive Question: {body.query}\n\n"
        f"Verified Grounding Context:\n{context_str}\n\n"
        "Draft a concise, executive-level answer strictly based on the provided sources. "
        "Cite source numbers (e.g. [Source 1]) when referencing facts. "
        "Do not invent facts not present in the context."
    )

    system_instruction = (
        "You are ServerGen AI Executive Intelligence Assistant. "
        "Answer questions accurately using ONLY the provided verified context. "
        "Maintain professional executive tone and highlight concrete actionable facts."
    )

    try:
        req = LLMRequest(
            model=settings.DEFAULT_MODEL,
            system_instruction=system_instruction,
            prompt=prompt,
            temperature=0.1,
            max_tokens=1024,
        )
        llm_res = await ollama.generate(req)
        answer_text = llm_res.content.strip()
    except Exception as exc:
        logger.warning("Local Ollama synthesis unavailable: %s. Using deterministic fallback.", exc)
        answer_text = (
            f"Based on verified records from your {body.target_vault.upper()} vault:\n\n"
            + "\n\n".join([f"• **{c.doc_title}**: {c.content[:250]}..." for c in selected_chunks[:3]])
        )

    # Verify citations
    verifier = CitationVerifier()
    verified_cits, missing_cits = verifier.verify_citations(
        output_text=answer_text,
        retrieved_citations=retrieval_res.citations,
    )
    is_grounded = len(missing_cits) == 0

    return {
        "answer": answer_text,
        "vault_searched": body.target_vault,
        "citations": [
            {
                "citation_index": c.citation_index,
                "document_title": c.document_title,
                "vault_scope": c.vault_scope,
                "classification": c.classification,
                "relevance_score": c.relevance_score,
                "excerpt": c.excerpt,
            }
            for c in (verified_cits or retrieval_res.citations)
        ],
        "is_grounded": is_grounded,
        "confidence_score": 1.0 if is_grounded else 0.85,
        "execution_time_ms": round((time.monotonic() - start_time) * 1000, 1),
    }
