"""
ServerGen AI — Spreadsheet & Excel Analytics REST API.

Provides endpoints for:
- Uploading and securely indexing multi-sheet Excel (.xlsx, .xls) and CSV workbooks
- Executing deterministic mathematical and statistical aggregations (totals, averages, group by, filters)
- Synthesizing deep AI executive insights grounded in verified tabular metrics
- Exporting styled transformed Excel files, PDF reports, and PowerPoint presentations
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.schemas import DataSensitivity
from src.auth.permissions import PermissionCode
from src.auth.rbac import AuthContext, require_permission
from src.core.database import get_db
from src.core.exceptions import ValidationError
from src.rag.storage import DocumentStorage
from src.services.audit_service import AuditEventType, AuditService
from src.services.docgen_service import DocumentGeneratorService
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

    # 3. Store file atomically via DocumentStorageBackend
    doc_id = uuid.uuid4()
    meta = storage_backend.save_file(
        document_id=doc_id,
        version_number=1,
        filename=file.filename or "spreadsheet.xlsx",
        content=content,
    )

    # 4. Parse workbook structure
    try:
        wb_data = spreadsheet_service.parse_content(content, file.filename or "spreadsheet.xlsx")
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
            "file_size": meta.file_size,
            "sheets_count": len(wb_data.sheet_names),
            "classification": sensitivity.value,
        },
    )
    await db.commit()

    return {
        "status": "success",
        "document_id": str(doc_id),
        "filename": file.filename,
        "classification": sensitivity.value,
        "file_size": meta.file_size,
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
