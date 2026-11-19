"""
ServerGen AI — Enterprise Refinements & Industry-Grade Features Test Suite.

Verifies:
1. Enterprise Zero-Trust Data Loss Prevention (DLP) & PII Redaction
2. Outlier & Anomaly Detection Engine (IQR and Z-Score algorithms)
3. Period-over-Period & Budget Variance Analysis Engine
4. Native PowerPoint (PPTX) Visual Chart and KPI Stat Card slide generation
5. ReportLab PDF Vector Bar Chart data report generation
6. End-to-end REST API endpoints for enterprise analytics & multi-format exports
"""

from __future__ import annotations

import io
import uuid

import pytest
from httpx import AsyncClient
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.security import create_access_token, hash_password
from src.models.role import Role
from src.models.user import User
from src.services.docgen_service import DocumentGeneratorService
from src.services.pii_service import EnterprisePIIService, pii_service
from src.services.spreadsheet_service import SheetData, SpreadsheetAnalyticsService


def _create_sample_financial_sheet() -> SheetData:
    headers = ["Department", "Budget", "Actual", "Contact_Email", "Employee_SSN"]
    rows = [
        ["Engineering", 120000.0, 122000.0, "alice@enterprise.org", "111-22-3333"],
        ["Sales", 85000.0, 87000.0, "bob@enterprise.org", "222-33-4444"],
        ["Marketing", 50000.0, 51000.0, "carol@enterprise.org", "333-44-5555"],
        ["Security", 60000.0, 350000.0, "dan@enterprise.org", "444-55-6666"],  # Major anomaly
        ["Legal", 40000.0, 41000.0, "elena@enterprise.org", "555-66-7777"],
        ["Operations", 70000.0, 72000.0, "frank@enterprise.org", "777-88-9999"],
    ]
    columns = {h: [r[i] for r in rows] for i, h in enumerate(headers)}
    service = SpreadsheetAnalyticsService()
    profiles = service._profile_columns(headers, columns)
    return SheetData(
        name="Q3_Financials",
        headers=headers,
        rows=rows,
        columns=columns,
        column_profiles=profiles,
    )


def test_pii_redaction_engine():
    """Verify zero-trust regex matching for PII, emails, SSNs, credit cards, and secrets."""
    svc = EnterprisePIIService()

    raw_text = (
        "Employee John (SSN: 123-45-6789, email: john.doe@fintech.io, phone: +1-555-839-2001) "
        "processed transaction with card 4111 2222 3333 4444 using token Bearer eyJhbGciOiJIUzI1NiJ9.secretKeyToken."
    )
    result = svc.redact_text(raw_text)

    assert result.redactions_count >= 5
    assert "[REDACTED_SSN]" in result.sanitized_text
    assert "[REDACTED_EMAIL]" in result.sanitized_text
    assert "[REDACTED_PHONE]" in result.sanitized_text
    assert "[REDACTED_CARD]" in result.sanitized_text
    assert "[REDACTED_SECRET]" in result.sanitized_text
    assert "john.doe@fintech.io" not in result.sanitized_text
    assert "123-45-6789" not in result.sanitized_text


def test_table_pii_redaction():
    """Verify tabular DLP scrubbing across rows and headers."""
    sheet = _create_sample_financial_sheet()
    clean_headers, clean_rows, redactions = pii_service.redact_table(sheet.headers, sheet.rows)

    assert redactions >= 12  # 6 emails + 6 SSNs
    for row in clean_rows:
        assert "[REDACTED_EMAIL]" in str(row[3])
        assert "[REDACTED_SSN]" in str(row[4])
        assert "@" not in str(row[3])


def test_anomaly_detection_iqr_and_zscore():
    """Verify statistical outlier detection on unexpected expenditure spikes."""
    sheet = _create_sample_financial_sheet()
    svc = SpreadsheetAnalyticsService()

    # IQR Method on 'Actual' expenses (Security at 185k is an outlier)
    headers, rows, metrics = svc.detect_anomalies(
        sheet,
        target_column="Actual",
        dimension_col="Department",
        method="iqr",
    )

    assert metrics["anomalies_detected"] >= 1
    assert any("Security" in str(r[0]) for r in rows)
    assert rows[0][2] == "High Outlier"
    assert rows[0][3] in ("CRITICAL", "ELEVATED")

    # Z-Score Method
    z_headers, z_rows, z_metrics = svc.detect_anomalies(
        sheet,
        target_column="Actual",
        dimension_col="Department",
        method="zscore",
        threshold=1.5,
    )
    assert z_metrics["anomalies_detected"] >= 1


def test_variance_analysis_engine():
    """Verify Budget vs Actual period-over-period delta calculation."""
    sheet = _create_sample_financial_sheet()
    svc = SpreadsheetAnalyticsService()

    headers, rows, metrics = svc.analyze_variance(
        sheet,
        base_col="Budget",
        comparison_col="Actual",
        dimension_col="Department",
    )

    assert "Variance ($)" in headers
    assert "Variance (%)" in headers
    assert "Performance" in headers
    assert metrics["total_base"] == 425000.0
    assert metrics["total_comparison"] == 723000.0
    assert metrics["net_variance"] == 298000.0

    # Top variance should be Security (+290,000)
    top_row = rows[0]
    assert top_row[0] == "Security"
    assert "+290,000.00" in str(top_row[3])


def test_chart_specification_extraction():
    """Verify extraction of categories and series for visual rendering."""
    sheet = _create_sample_financial_sheet()
    svc = SpreadsheetAnalyticsService()

    spec = svc.extract_chart_spec(sheet.headers, sheet.rows)
    assert len(spec["categories"]) == 6
    assert spec["categories"][0] == "Engineering"
    assert len(spec["series"]) >= 2
    assert spec["series"][0]["name"] == "Budget"
    assert spec["series"][1]["name"] == "Actual"


def test_native_pptx_chart_data_deck(tmp_path):
    """Verify generation of widescreen 16:9 PPTX with native editable PowerPoint charts and KPI cards."""
    docgen = DocumentGeneratorService(storage_dir=tmp_path)
    sheet = _create_sample_financial_sheet()

    out_path, meta = docgen.render_executive_data_deck(
        title="Q3 Enterprise Financial Review",
        subtitle="Departmental Budget vs Actual Variance",
        table_headers=sheet.headers[:3],
        table_rows=[r[:3] for r in sheet.rows],
        executive_insights="Critical cost overrun detected in Security. Engineering performance aligned.",
        classification="RESTRICTED",
    )

    assert out_path.exists()
    assert out_path.stat().st_size > 15000
    assert meta.format == "pptx"
    assert meta.slide_or_page_count == 5


def test_pdf_vector_chart_data_report(tmp_path):
    """Verify generation of executive PDF with ReportLab vector bar charts."""
    docgen = DocumentGeneratorService(storage_dir=tmp_path)
    sheet = _create_sample_financial_sheet()

    out_path, meta = docgen.render_executive_data_report(
        title="Fiscal Operations Brief",
        subtitle="Operational Distribution & Variance",
        table_headers=sheet.headers[:3],
        table_rows=[r[:3] for r in sheet.rows],
        executive_insights="Executive review shows 98% conformance with budget milestones.",
        classification="CONFIDENTIAL",
    )

    assert out_path.exists()
    assert out_path.stat().st_size > 2000
    assert meta.format == "pdf"


async def _setup_admin(db: AsyncSession) -> tuple[str, str]:
    res = await db.execute(select(Role).where(Role.name == "administrator"))
    existing_role = res.scalar_one_or_none()
    if existing_role is None:
        role = Role(id=uuid.uuid4(), name="administrator", description="Admin role")
        db.add(role)
        await db.flush()
        existing_role = role

    admin = User(
        id=uuid.uuid4(),
        username=f"admin_ind_{uuid.uuid4().hex[:6]}",
        email=f"admin_ind_{uuid.uuid4().hex[:6]}@test.local",
        hashed_password=hash_password("AdminPass123!"),
        role_id=existing_role.id,
        is_active=True,
    )
    db.add(admin)
    await db.commit()
    token = create_access_token(user_id=str(admin.id), role="administrator")
    return token, str(admin.id)


@pytest.mark.asyncio
async def test_api_anomaly_and_variance_lifecycle(client: AsyncClient, db_session: AsyncSession):
    """End-to-end API test verifying upload, anomaly scan, variance analysis, and PPTX chart export."""
    token, _ = await _setup_admin(db_session)
    auth_headers = {"Authorization": f"Bearer {token}"}

    # 1. Create and Upload XLSX
    wb = Workbook()
    ws = wb.active
    ws.title = "Cost_Centers"
    ws.append(["Department", "Q1_Budget", "Q1_Actual", "Owner_Email"])
    ws.append(["Platform", 50000.0, 52000.0, "platform@corp.local"])
    ws.append(["Infrastructure", 80000.0, 245000.0, "infra@corp.local"])  # High outlier
    ws.append(["AppDev", 45000.0, 44000.0, "appdev@corp.local"])
    ws.append(["QA_Testing", 30000.0, 31000.0, "qa@corp.local"])
    ws.append(["DevOps", 40000.0, 42000.0, "devops@corp.local"])
    ws.append(["SecurityOps", 55000.0, 54000.0, "secops@corp.local"])
    buf = io.BytesIO()
    wb.save(buf)

    files = {
        "file": ("enterprise_costs.xlsx", io.BytesIO(buf.getvalue()), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    }
    data = {"title": "Enterprise Cost Sheet", "classification": "internal"}
    res_up = await client.post("/api/v1/spreadsheets/upload", data=data, files=files, headers=auth_headers)
    assert res_up.status_code == 200
    doc_id = res_up.json()["document_id"]

    # 2. Test Anomaly Detection API
    anom_payload = {
        "document_id": doc_id,
        "sheet_name": "Cost_Centers",
        "operation": "anomaly",
        "target_column": "Q1_Actual",
        "dimension_column": "Department",
        "mask_pii": True,
    }
    res_anom = await client.post("/api/v1/spreadsheets/analyze", json=anom_payload, headers=auth_headers)
    assert res_anom.status_code == 200
    anom_json = res_anom.json()
    assert anom_json["status"] == "success"
    assert "chart_spec" in anom_json
    assert anom_json["metrics"]["anomalies_detected"] >= 1

    # 3. Test Variance Analysis API
    var_payload = {
        "document_id": doc_id,
        "sheet_name": "Cost_Centers",
        "operation": "variance",
        "base_column": "Q1_Budget",
        "comparison_column": "Q1_Actual",
        "dimension_column": "Department",
        "mask_pii": True,
    }
    res_var = await client.post("/api/v1/spreadsheets/analyze", json=var_payload, headers=auth_headers)
    assert res_var.status_code == 200
    var_json = res_var.json()
    assert var_json["status"] == "success"
    assert "Variance ($)" in var_json["table_headers"]

    # 4. Export to Native PPTX Deck
    export_payload = {
        "document_id": doc_id,
        "sheet_name": "Cost_Centers",
        "export_format": "pptx",
        "title": "Cost Variance & Outlier Briefing",
        "table_headers": var_json["table_headers"],
        "table_rows": var_json["table_rows"],
        "executive_insights": var_json["executive_insights"],
    }
    res_ex = await client.post("/api/v1/spreadsheets/export", json=export_payload, headers=auth_headers)
    assert res_ex.status_code == 200
    assert res_ex.json()["format"] == "pptx"
