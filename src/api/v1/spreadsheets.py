"""
ServerGen AI — Spreadsheet & Excel Analytics REST API.

Provides endpoints for:
- Uploading and securely indexing multi-sheet Excel (.xlsx, .xls) and CSV workbooks
- Executing deterministic mathematical and statistical aggregations (totals, averages, group by, filters)
- Synthesizing deep AI executive insights grounded in verified tabular metrics
- Exporting styled transformed Excel files, PDF reports, and PowerPoint presentations
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.schemas import DataSensitivity
from src.auth.permissions import PermissionCode
from src.auth.rbac import AuthContext, require_permission
from src.core.database import get_db
from src.core.exceptions import ValidationError
from src.models.analysis_history import AnalysisHistory
from src.models.document import Document
from src.rag.storage import DocumentStorage
from src.services.audit_service import AuditEventType, AuditService
from src.services.docgen_service import DocumentGeneratorService
from src.services.nl_analytics_service import NLAnalyticsService
from src.services.pii_service import pii_service
from src.services.spreadsheet_service import SpreadsheetAnalyticsService

logger = logging.getLogger("servergen.api.spreadsheets")

router = APIRouter(prefix="/api/v1/spreadsheets", tags=["Spreadsheet & Excel Analytics"])

spreadsheet_service = SpreadsheetAnalyticsService()
storage_backend = DocumentStorage()
docgen_service = DocumentGeneratorService()


# ── Pydantic Request & Response Models ──────────────────────────────────────


class AnalyzeRequest(BaseModel):
    document_id: str = Field(..., description="Document ID of the uploaded spreadsheet")
    sheet_name: str | None = Field(default=None, description="Specific tab name (defaults to first tab)")
    operation: str = Field(default="overview", description="'overview', 'groupby', 'filter', 'anomaly', or 'variance'")
    group_column: str | None = Field(default=None, description="Column to group by for 'groupby' operation")
    aggregations: list[dict[str, str]] = Field(
        default_factory=list,
        description="e.g. [{'column': 'Revenue', 'op': 'sum'}, {'column': 'Margin', 'op': 'avg'}]",
    )
    filter_column: str | None = None
    operator: str = "=="
    filter_value: Any = None
    sort_column: str | None = None
    ascending: bool = False
    target_column: str | None = Field(default=None, description="Target column for outlier/anomaly detection")
    anomaly_method: str = Field(default="iqr", description="'iqr' or 'zscore'")
    base_column: str | None = Field(default=None, description="Base column for variance analysis")
    comparison_column: str | None = Field(default=None, description="Comparison column for variance analysis")
    dimension_column: str | None = Field(default=None, description="Category/dimension column")
    mask_pii: bool = Field(default=False, description="Apply enterprise zero-trust PII redaction")
    prompt: str | None = Field(default=None, description="Custom prompt to guide executive insight synthesis")


class ExportSpreadsheetRequest(BaseModel):
    document_id: str
    sheet_name: str | None = None
    export_format: str = Field(default="xlsx", description="'xlsx', 'pdf', or 'pptx'")
    title: str = Field(default="Spreadsheet Executive Analysis")
    table_headers: list[str] = Field(default_factory=list)
    table_rows: list[list[Any]] = Field(default_factory=list)
    executive_insights: str = ""


# ── 1. Upload Spreadsheet ───────────────────────────────────────────────────


@router.post("/upload")
async def upload_spreadsheet(
    file: Annotated[UploadFile, File(...)],
    title: Annotated[str, Form(...)],
    classification: Annotated[str, Form()] = "internal",
    auth: AuthContext = Depends(require_permission(PermissionCode.DOCUMENT_UPLOAD)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Upload and inspect an Excel (.xlsx) or CSV spreadsheet file into managed storage."""
    audit = AuditService(db)

    # 1. Validate classification
    try:
        sensitivity = DataSensitivity(classification.lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid classification '{classification}'. Must be public, internal, confidential, or restricted.",
        ) from exc

    # 2. Read bytes
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # 3. Parse workbook structure
    try:
        wb_data = spreadsheet_service.parse_content(content, file.filename or "spreadsheet.xlsx")
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 4. Store file & create Document entity atomically
    vault_scope = "manager" if sensitivity.value in ("confidential", "restricted") and auth.role == "manager" else "all"
    try:
        from src.rag.service import DocumentService

        doc_service = DocumentService(db)
        doc, version, _ = await doc_service.create_document_with_file(
            auth=auth,
            filename=file.filename or "spreadsheet.xlsx",
            content=content,
            title=title or file.filename,
            category="spreadsheet",
            classification=sensitivity.value,
            vault_scope=vault_scope,
            description=f"Spreadsheet workbook with {len(wb_data.sheet_names)} sheet(s)",
            auto_index=False,
        )
        doc_id = doc.id
        file_size = version.file_size
    except Exception as exc:
        logger.warning("DocumentService registration fallback: %s", exc)
        doc_id = uuid.uuid4()
        meta = storage_backend.save_file(
            document_id=doc_id,
            version_number=1,
            filename=file.filename or "spreadsheet.xlsx",
            content=content,
        )
        file_size = meta.file_size

    # 5. Build summary of all sheets
    sheets_info = []
    for sname in wb_data.sheet_names:
        s = wb_data.sheets[sname]
        sheets_info.append({
            "name": sname,
            "row_count": s.row_count(),
            "col_count": s.col_count(),
            "headers": s.headers,
            "numeric_columns": [h for h, p in s.column_profiles.items() if p.inferred_type == "numeric"],
        })

    # 6. Record audit event
    await audit.record(
        event_type=AuditEventType.DOCUMENT_UPLOAD,
        action="spreadsheet.upload",
        request_id=str(uuid.uuid4()),
        user_id=auth.user_id,
        role=auth.role,
        resource=str(doc_id),
        metadata={
            "filename": file.filename,
            "file_size": file_size,
            "sheets_count": len(wb_data.sheet_names),
            "classification": sensitivity.value,
        },
    )
    await db.commit()

    # Dispatch spreadsheet upload notification
    try:
        from src.services.notification_service import NotificationService

        notif_svc = NotificationService(db)
        await notif_svc.notify_user(
            recipient_user_id=auth.user_id,
            event_type="document_uploaded",
            title="Spreadsheet Ingested",
            message=f"Uploaded '{file.filename}' ({len(wb_data.sheet_names)} sheet(s) detected).",
            related_resource_type="spreadsheet",
            related_resource_id=str(doc_id),
            priority="low",
        )
        await db.commit()
    except Exception as e:
        logger.debug("Spreadsheet upload notification skipped: %s", e)

    return {
        "status": "success",
        "document_id": str(doc_id),
        "filename": file.filename,
        "classification": sensitivity.value,
        "file_size": file_size,
        "sheets_count": len(wb_data.sheet_names),
        "sheets": sheets_info,
    }


# ── 2. Deep Tabular Analysis ────────────────────────────────────────────────


@router.post("/analyze")
async def analyze_spreadsheet(
    request: AnalyzeRequest,
    auth: AuthContext = Depends(require_permission(PermissionCode.AI_EXECUTE)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Execute high-precision calculations, grouped aggregations, and AI insights on a stored sheet."""
    audit = AuditService(db)

    # 1. Resolve stored document
    try:
        doc_uuid = uuid.UUID(request.document_id)
        doc_dir = storage_backend.base_dir / str(doc_uuid) / "1"
        files = list(doc_dir.glob("*")) if doc_dir.exists() else []
        if not files:
            files = list((storage_backend.base_dir / "vaults").glob(f"*/{doc_uuid}/1/*"))
        if not files:
            raise FileNotFoundError("No files in document directory")
        file_path = files[0]
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Spreadsheet document not found in storage.") from exc

    content = file_path.read_bytes()
    wb_data = spreadsheet_service.parse_content(content, file_path.name)

    target_sheet = (
        wb_data.sheets.get(request.sheet_name)
        if request.sheet_name and request.sheet_name in wb_data.sheets
        else wb_data.sheets[wb_data.sheet_names[0]]
    )

    overview_md = spreadsheet_service.generate_overview_markdown(target_sheet)

    # 2. Execute requested operation
    metrics: dict[str, Any] = {}
    if request.operation == "groupby" and request.group_column:
        aggs = request.aggregations or [{"column": target_sheet.headers[-1], "op": "sum"}]
        headers, rows = spreadsheet_service.group_by_aggregate(target_sheet, request.group_column, aggs)
    elif request.operation == "filter":
        headers, rows = spreadsheet_service.filter_and_sort(
            target_sheet,
            filter_col=request.filter_column,
            operator=request.operator,
            filter_val=request.filter_value,
            sort_col=request.sort_column,
            ascending=request.ascending,
        )
    elif request.operation == "anomaly" and request.target_column:
        headers, rows, metrics = spreadsheet_service.detect_anomalies(
            target_sheet,
            target_column=request.target_column,
            dimension_col=request.dimension_column,
            method=request.anomaly_method,
        )
    elif request.operation == "variance" and request.base_column and request.comparison_column:
        headers, rows, metrics = spreadsheet_service.analyze_variance(
            target_sheet,
            base_col=request.base_column,
            comparison_col=request.comparison_column,
            dimension_col=request.dimension_column,
        )
    else:
        # Default: sample data view with all headers
        headers = target_sheet.headers
        rows = target_sheet.rows[:30]

    # Optional zero-trust PII scrubbing
    pii_redactions = 0
    if request.mask_pii:
        headers, rows, pii_redactions = pii_service.redact_table(headers, rows)

    data_table_md = spreadsheet_service.format_markdown_table(headers, rows)

    # 3. Generate grounded executive insights
    insights = await spreadsheet_service.generate_executive_insights(
        sheet_name=target_sheet.name,
        overview_md=overview_md,
        data_table_md=data_table_md,
        user_prompt=request.prompt,
        mask_pii=request.mask_pii,
    )

    # Extract Chart Specification for UI and downstream charting
    chart_spec = spreadsheet_service.extract_chart_spec(headers, rows)

    # 4. Audit ledger entry
    await audit.record(
        event_type=AuditEventType.EXECUTION_COMPLETED,
        action="spreadsheet.analyze",
        request_id=str(uuid.uuid4()),
        user_id=auth.user_id,
        role=auth.role,
        resource=request.document_id,
        metadata={
            "sheet_name": target_sheet.name,
            "operation": request.operation,
            "rows_evaluated": target_sheet.row_count(),
            "pii_redacted": pii_redactions,
        },
    )
    await db.commit()

    # Dispatch spreadsheet analysis notification
    try:
        from src.services.notification_service import NotificationService

        notif_svc = NotificationService(db)
        await notif_svc.notify_user(
            recipient_user_id=auth.user_id,
            event_type="analytics_completed",
            title="Spreadsheet Analysis Completed",
            message=(
                f"Analysis of '{target_sheet.name}' ({request.operation}) "
                f"completed successfully."
            ),
            related_resource_type="spreadsheet",
            related_resource_id=request.document_id,
            priority="low",
        )
        await db.commit()
    except Exception as e:
        logger.debug("Spreadsheet analysis notification skipped: %s", e)

    return {
        "status": "success",
        "document_id": request.document_id,
        "sheet_name": target_sheet.name,
        "available_sheets": wb_data.sheet_names,
        "row_count": target_sheet.row_count(),
        "col_count": target_sheet.col_count(),
        "overview_markdown": overview_md,
        "data_table_markdown": data_table_md,
        "table_headers": headers,
        "table_rows": rows,
        "chart_spec": chart_spec,
        "metrics": metrics,
        "pii_redacted_count": pii_redactions,
        "executive_insights": insights,
    }


# ── 3. Export Transformed Sheet / PDF / PPTX ─────────────────────────────────


@router.post("/export")
async def export_spreadsheet_analysis(
    request: ExportSpreadsheetRequest,
    auth: AuthContext = Depends(require_permission(PermissionCode.AI_EXECUTE)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Generate and export a styled Excel file, PDF executive report, or PowerPoint deck."""
    fmt = request.export_format.lower()

    if fmt == "xlsx":
        out_path = spreadsheet_service.export_styled_xlsx(
            sheet_name=request.sheet_name or "Analytics_Export",
            headers=request.table_headers,
            rows=request.table_rows,
            title=request.title,
        )
        file_id = out_path.stem.split("_")[0]
        return {
            "status": "success",
            "format": "xlsx",
            "filename": out_path.name,
            "file_size": out_path.stat().st_size,
            "download_url": f"/api/v1/generate/download/{file_id}",
        }

    elif fmt == "pdf":
        out_path, meta = docgen_service.render_executive_data_report(
            title=request.title,
            subtitle=f"Tabular Operations Report — {request.sheet_name or 'Sheet'}",
            table_headers=request.table_headers,
            table_rows=request.table_rows,
            executive_insights=request.executive_insights,
            classification="INTERNAL",
        )
        return {
            "status": "success",
            "format": "pdf",
            "filename": meta.filename,
            "file_size": meta.file_size,
            "download_url": meta.download_url,
        }

    elif fmt == "pptx":
        out_path, meta = docgen_service.render_executive_data_deck(
            title=request.title,
            subtitle=f"Executive Data Analysis — {request.sheet_name or 'Sheet'}",
            table_headers=request.table_headers,
            table_rows=request.table_rows,
            executive_insights=request.executive_insights,
            classification="INTERNAL",
        )
        return {
            "status": "success",
            "format": "pptx",
            "filename": meta.filename,
            "file_size": meta.file_size,
            "download_url": meta.download_url,
        }

    else:
        raise HTTPException(status_code=400, detail="Supported export formats: 'xlsx', 'pdf', 'pptx'.")


# ── 4. Unified Prompt-First Autonomous Workflow ─────────────────────────────


@router.post("/auto-workflow")
async def execute_autonomous_spreadsheet_workflow(
    file: UploadFile | None = File(None),
    document_id: str | None = Form(None),
    prompt: str = Form(""),
    sheet_name: str | None = Form(None),
    mask_pii: bool = Form(False),
    title: str | None = Form(None),
    auth: AuthContext = Depends(require_permission(PermissionCode.AI_EXECUTE)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Unified Autonomous Prompt-First Spreadsheet Workflow.

    In a single automated transaction:
    1. Ingests or resolves the Excel/CSV spreadsheet.
    2. Dynamically routes analytical operations based on user prompt (anomalies, variance, groupby, or overview).
    3. Computes statistical metrics and builds 3 standardized KPI stat cards.
    4. Extracts Chart.js compatible visual specifications.
    5. Synthesizes grounded AI executive narrative insights via local LLM.
    6. Automatically renders and delivers all 3 deliverables:
       - 16:9 PowerPoint Presentation (.pptx) with native editable charts
       - Executive Audit Report (.pdf) with vector charts
       - Formatted, styled Excel Workbook (.xlsx)
    """
    audit = AuditService(db)

    # 1. Resolve spreadsheet content & doc_id
    if file and file.filename:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded spreadsheet file is empty.")
        doc_uuid = uuid.uuid4()
        try:
            storage_backend.save_file(
                document_id=doc_uuid,
                version_number=1,
                filename=file.filename,
                content=content,
            )
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        target_filename = file.filename
    elif document_id:
        try:
            doc_uuid = uuid.UUID(document_id)
            doc_dir = storage_backend.base_dir / str(doc_uuid) / "1"
            files = list(doc_dir.glob("*")) if doc_dir.exists() else []
            if not files:
                files = list((storage_backend.base_dir / "vaults").glob(f"*/{doc_uuid}/1/*"))
            if not files:
                raise FileNotFoundError("No files in document directory")
            file_path = files[0]
            content = file_path.read_bytes()
            target_filename = file_path.name
        except Exception as exc:
            raise HTTPException(status_code=404, detail="Spreadsheet document not found in storage.") from exc
    else:
        raise HTTPException(
            status_code=400,
            detail="Must provide either a spreadsheet file upload or an existing document_id.",
        )

    # 2. Parse workbook
    try:
        wb_data = spreadsheet_service.parse_content(content, target_filename)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 3. Select target sheet
    target_sheet = (
        wb_data.sheets.get(sheet_name)
        if sheet_name and sheet_name in wb_data.sheets
        else wb_data.sheets[wb_data.sheet_names[0]]
    )

    # 4. Autonomous analysis and routing
    route_res = spreadsheet_service.auto_analyze_and_route(
        sheet=target_sheet,
        prompt=prompt,
        mask_pii=mask_pii,
    )

    overview_md = spreadsheet_service.generate_overview_markdown(target_sheet)

    # 5. Synthesize grounded executive insights with local Ollama LLM
    insights = await spreadsheet_service.generate_executive_insights(
        sheet_name=target_sheet.name,
        overview_md=overview_md,
        data_table_md=route_res["data_table_md"],
        user_prompt=prompt,
        mask_pii=mask_pii,
    )

    workflow_title = title or route_res["headline"]

    # 6. Generate Deliverables: PPTX, PDF, and styled XLSX
    _pptx_path, pptx_meta = docgen_service.render_executive_data_deck(
        title=workflow_title,
        subtitle=f"Autonomous Analysis — {target_sheet.name}",
        table_headers=route_res["headers"],
        table_rows=route_res["rows"],
        executive_insights=insights,
        classification="INTERNAL",
    )

    _pdf_path, pdf_meta = docgen_service.render_executive_data_report(
        title=workflow_title,
        subtitle=f"Autonomous Audit Report — {target_sheet.name}",
        table_headers=route_res["headers"],
        table_rows=route_res["rows"],
        executive_insights=insights,
        classification="INTERNAL",
    )

    xlsx_path = spreadsheet_service.export_styled_xlsx(
        sheet_name=target_sheet.name,
        headers=route_res["headers"],
        rows=route_res["rows"],
        title=workflow_title,
    )
    xlsx_file_id = xlsx_path.stem.split("_")[0]

    # 7. Audit ledger
    await audit.record(
        event_type=AuditEventType.EXECUTION_COMPLETED,
        action="spreadsheet.auto_workflow",
        request_id=str(uuid.uuid4()),
        user_id=auth.user_id,
        role=auth.role,
        resource=str(doc_uuid),
        metadata={
            "filename": target_filename,
            "mode": route_res["mode"],
            "sheet_name": target_sheet.name,
            "prompt": prompt,
            "pii_redacted": route_res["pii_redacted_count"],
        },
    )
    await db.commit()

    # Dispatch spreadsheet analysis notification
    try:
        from src.services.notification_service import NotificationService

        notif_svc = NotificationService(db)
        await notif_svc.notify_user(
            recipient_user_id=auth.user_id,
            event_type="analytics_completed",
            title="Autonomous Analysis Completed",
            message=(
                f"Autonomous workflow for '{target_sheet.name}' ({route_res['mode']}) "
                f"completed successfully."
            ),
            related_resource_type="spreadsheet",
            related_resource_id=str(doc_uuid),
            priority="low",
        )
        await db.commit()
    except Exception as e:
        logger.debug("Spreadsheet analysis notification skipped: %s", e)

    return {
        "status": "success",
        "document_id": str(doc_uuid),
        "filename": target_filename,
        "sheet_name": target_sheet.name,
        "available_sheets": wb_data.sheet_names,
        "mode": route_res["mode"],
        "headline": workflow_title,
        "row_count": target_sheet.row_count(),
        "col_count": target_sheet.col_count(),
        "kpi_metrics": route_res["kpis"],
        "chart_spec": route_res["chart_spec"],
        "table_headers": route_res["headers"],
        "table_rows": route_res["rows"],
        "executive_insights": insights,
        "pii_redacted_count": route_res["pii_redacted_count"],
        "deliverables": {
            "pptx": {
                "download_url": pptx_meta.download_url,
                "filename": pptx_meta.filename,
                "file_size": pptx_meta.file_size,
            },
            "pdf": {
                "download_url": pdf_meta.download_url,
                "filename": pdf_meta.filename,
                "file_size": pdf_meta.file_size,
            },
            "xlsx": {
                "download_url": f"/api/v1/generate/download/{xlsx_file_id}",
                "filename": xlsx_path.name,
                "file_size": xlsx_path.stat().st_size,
            },
        },
    }


# ── Helper: Storage Path Resolver ───────────────────────────────────────────


def _resolve_spreadsheet_path(doc_uuid: uuid.UUID) -> Path | None:
    """Resolve file path across standard storage and role-vault trees."""
    doc_dir = storage_backend.base_dir / str(doc_uuid) / "1"
    files = (
        [f for f in doc_dir.glob("*") if f.is_file() and not f.name.endswith(".txt")]
        if doc_dir.exists()
        else []
    )
    if not files:
        files = [
            f
            for f in (storage_backend.base_dir / "vaults").glob(f"*/{doc_uuid}/1/*")
            if f.is_file() and not f.name.endswith(".txt")
        ]
    return files[0] if files else None


# ── 5. Natural Language Data Analysis Endpoints ─────────────────────────────


class NLQueryRequest(BaseModel):
    document_id: str = Field(..., description="Uploaded spreadsheet document ID")
    sheet_name: str | None = Field(
        default=None, description="Specific sheet tab (defaults to first tab)"
    )
    question: str = Field(..., description="Plain English analytical question")
    mask_pii: bool = Field(default=False, description="Apply enterprise zero-trust PII redaction")


@router.post("/nl-query")
async def execute_natural_language_query(
    request: NLQueryRequest,
    auth: AuthContext = Depends(require_permission(PermissionCode.DOCUMENT_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Execute plain-English natural language queries against authorized Excel/CSV spreadsheets.
    - Role-vault clearance checks prevent horizontal privilege escalation.
    - Deterministic numerical calculations run via Python, Pandas, and NumPy.
    - Local LLM explains results; Chart.js specs enable instant visualization.
    """
    audit = AuditService(db)

    try:
        doc_uuid = uuid.UUID(request.document_id)
    except ValueError as err:
        raise HTTPException(status_code=400, detail="Invalid document ID format.") from err

    # 1. Role-vault clearance enforcement
    stmt = select(Document).where(Document.id == doc_uuid, Document.is_deleted.is_(False))
    res = await db.execute(stmt)
    doc_entity = res.scalar_one_or_none()
    if not doc_entity:
        raise HTTPException(status_code=404, detail="Spreadsheet document not found.")

    if doc_entity.vault_scope == "manager" and auth.role not in ("manager", "administrator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Document is secured within the Manager Confidential Vault.",
        )

    # 2. Resolve file path
    file_path = _resolve_spreadsheet_path(doc_uuid)
    if not file_path:
        raise HTTPException(status_code=404, detail="Spreadsheet file not found in storage.")

    content = file_path.read_bytes()
    wb_data = spreadsheet_service.parse_content(content, file_path.name)
    target_sheet = (
        wb_data.sheets.get(request.sheet_name)
        if request.sheet_name and request.sheet_name in wb_data.sheets
        else next(iter(wb_data.sheets.values()))
    )

    # 3. Execute natural language analysis
    nl_service = NLAnalyticsService(db)
    result = await nl_service.analyze_question(
        sheet=target_sheet,
        question=request.question,
        user_id=auth.user_id,
        document_id=doc_uuid,
        mask_pii=request.mask_pii,
    )

    # 4. Audit ledger
    await audit.record(
        event_type=AuditEventType.EXECUTION_COMPLETED,
        action="spreadsheet.nl_query",
        request_id=str(uuid.uuid4()),
        user_id=auth.user_id,
        role=auth.role,
        resource=str(doc_uuid),
        metadata={
            "question": request.question,
            "operation": result.operation,
            "sub_operation": result.sub_operation,
            "latency_ms": result.execution_time_ms,
        },
    )
    await db.commit()

    # 5. Dispatch notification
    try:
        from src.services.notification_service import NotificationService

        notif_svc = NotificationService(db)
        await notif_svc.notify_user(
            recipient_user_id=auth.user_id,
            event_type="analytics_completed",
            title="Natural Language Analysis Complete",
            message=f"Answered: '{request.question[:60]}' on '{target_sheet.name}'",
            related_resource_type="spreadsheet",
            related_resource_id=str(doc_uuid),
            priority="low",
        )
        await db.commit()
    except Exception as e:
        logger.debug("NL analytics notification skipped: %s", e)

    return {
        "status": "success",
        "document_id": str(doc_uuid),
        "filename": file_path.name,
        "sheet_name": target_sheet.name,
        "available_sheets": wb_data.sheet_names,
        "question": result.question,
        "operation": result.operation,
        "sub_operation": result.sub_operation,
        "direct_answer": result.direct_answer,
        "executive_explanation": result.executive_explanation,
        "table_headers": result.table_headers,
        "table_rows": result.table_rows,
        "kpis": result.kpis,
        "metrics": result.metrics,
        "chart_spec": result.chart_spec,
        "row_count": result.row_count,
        "col_count": result.col_count,
        "execution_time_ms": result.execution_time_ms,
        "pii_redacted_count": result.pii_redacted_count,
        "answer": result.direct_answer,
        "explanation": result.executive_explanation,
        "data": {
            "columns": result.table_headers,
            "rows": result.table_rows,
            "row_count": len(result.table_rows),
        },
    }


@router.get("/{document_id}/schema")
async def get_spreadsheet_schema(
    document_id: str,
    sheet_name: str | None = None,
    auth: AuthContext = Depends(require_permission(PermissionCode.DOCUMENT_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Expose dataset columns, types, profile stats, and intelligent suggested questions
    for the natural language analysis workbench.
    """
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError as err:
        raise HTTPException(status_code=400, detail="Invalid document ID format.") from err

    # Clearance check
    stmt = select(Document).where(Document.id == doc_uuid, Document.is_deleted.is_(False))
    res = await db.execute(stmt)
    doc_entity = res.scalar_one_or_none()
    if not doc_entity:
        raise HTTPException(status_code=404, detail="Document not found.")

    if doc_entity.vault_scope == "manager" and auth.role not in ("manager", "administrator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Document is secured within the Manager Confidential Vault.",
        )

    file_path = _resolve_spreadsheet_path(doc_uuid)
    if not file_path:
        raise HTTPException(status_code=404, detail="Spreadsheet file not found in storage.")

    content = file_path.read_bytes()
    wb_data = spreadsheet_service.parse_content(content, file_path.name)
    target_sheet = (
        wb_data.sheets.get(sheet_name)
        if sheet_name and sheet_name in wb_data.sheets
        else next(iter(wb_data.sheets.values()))
    )

    columns = []
    numeric_cols = []
    categorical_cols = []
    for h in target_sheet.headers:
        prof = target_sheet.column_profiles.get(h)
        col_type = prof.inferred_type if prof else "text"
        if col_type in ("numeric", "currency", "percentage"):
            numeric_cols.append(h)
        else:
            categorical_cols.append(h)

        sample = prof.sample_values[:3] if prof else []
        columns.append({
            "name": h,
            "type": col_type,
            "non_null_count": prof.non_null_count if prof else 0,
            "null_count": prof.null_count if prof else 0,
            "sample_values": sample,
        })

    # Generate intelligent suggested questions
    suggested_questions = []
    if numeric_cols and categorical_cols:
        suggested_questions.append(
            f"Which {categorical_cols[0]} has the highest {numeric_cols[0]}?"
        )
        suggested_questions.append(
            f"Show the top 5 {categorical_cols[0]}s based on {numeric_cols[0]}"
        )
        suggested_questions.append(
            f"Compare {numeric_cols[0]} across all {categorical_cols[0]}s"
        )
    if numeric_cols:
        suggested_questions.append(f"Calculate the total {numeric_cols[0]} across all records")
        suggested_questions.append(f"Detect statistical outliers in {numeric_cols[0]}")
    if any("budget" in c.lower() for c in target_sheet.headers) and any(
        "actual" in c.lower() or "expense" in c.lower() for c in target_sheet.headers
    ):
        suggested_questions.append("Which departments exceeded their allocated budgets?")
        suggested_questions.append("Compare budget and actual expenses with variance percentages")
    suggested_questions.append("Find any duplicate records in this dataset")
    suggested_questions.append("Check for missing or blank values across columns")

    return {
        "document_id": str(doc_uuid),
        "filename": file_path.name,
        "vault_scope": doc_entity.vault_scope,
        "available_sheets": wb_data.sheet_names,
        "active_sheet": target_sheet.name,
        "row_count": target_sheet.row_count(),
        "col_count": target_sheet.col_count(),
        "columns": columns,
        "suggested_questions": suggested_questions,
    }


@router.get("/nl-history")
async def get_nl_analysis_history(
    document_id: str | None = None,
    limit: int = Query(20, ge=1, le=50),
    auth: AuthContext = Depends(require_permission(PermissionCode.DOCUMENT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Retrieve the recent natural language analysis history for the current user."""
    conditions = [AnalysisHistory.user_id == uuid.UUID(auth.user_id)]
    if document_id:
        with contextlib.suppress(ValueError):
            conditions.append(AnalysisHistory.document_id == uuid.UUID(document_id))

    stmt = (
        select(AnalysisHistory)
        .where(*conditions)
        .order_by(AnalysisHistory.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return [
        {
            "id": str(h.id),
            "document_id": str(h.document_id) if h.document_id else None,
            "sheet_name": h.sheet_name,
            "question": h.question,
            "analysis_type": h.analysis_type,
            "status": h.status,
            "result_summary": h.result_summary,
            "created_at": h.created_at.isoformat() if h.created_at else "",
        }
        for h in items
    ]

