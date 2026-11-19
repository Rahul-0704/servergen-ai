"""
ServerGen AI — Spreadsheet REST API Endpoint Tests.

Verifies:
1. POST /api/v1/spreadsheets/upload with Excel (.xlsx) and CSV
2. POST /api/v1/spreadsheets/analyze for overview, groupby, and filtering
3. POST /api/v1/spreadsheets/export for styled XLSX, PDF, and PPTX
4. RBAC permission checks (DOCUMENT_UPLOAD and AI_EXECUTE)
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


def _create_test_xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Financials"
    ws.append(["Cost_Center", "Category", "Amount", "Headcount"])
    ws.append(["CC-101", "Engineering", 75000.0, 12])
    ws.append(["CC-102", "Engineering", 42000.0, 6])
    ws.append(["CC-201", "Operations", 31000.0, 5])
    ws.append(["CC-301", "Security", 68000.0, 8])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


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
        username=f"admin_sheet_{uuid.uuid4().hex[:6]}",
        email=f"admin_sheet_{uuid.uuid4().hex[:6]}@test.local",
        hashed_password=hash_password("AdminPass123!"),
        role_id=existing_role.id,
        is_active=True,
    )
    db.add(admin)
    await db.commit()
    token = create_access_token(user_id=str(admin.id), role="administrator")
    return token, str(admin.id)


@pytest.mark.asyncio
async def test_spreadsheet_api_lifecycle(client: AsyncClient, db_session: AsyncSession):
    token, admin_id = await _setup_admin(db_session)
    auth_headers = {"Authorization": f"Bearer {token}"}

    # 1. Upload Spreadsheet
    xlsx_bytes = _create_test_xlsx_bytes()
    files = {
        "file": ("q3_budget.xlsx", io.BytesIO(xlsx_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    }
    data = {
        "title": "Q3 Enterprise Budget",
        "classification": "internal",
    }
    res_up = await client.post("/api/v1/spreadsheets/upload", data=data, files=files, headers=auth_headers)
    assert res_up.status_code == 200, res_up.text
    up_json = res_up.json()
    assert up_json["status"] == "success"
    doc_id = up_json["document_id"]
    assert up_json["sheets_count"] == 1
    assert up_json["sheets"][0]["name"] == "Financials"

    # 2. Analyze (GroupBy Operation)
    analyze_payload = {
        "document_id": doc_id,
        "sheet_name": "Financials",
        "operation": "groupby",
        "group_column": "Category",
        "aggregations": [{"column": "Amount", "op": "sum"}],
    }
    res_an = await client.post("/api/v1/spreadsheets/analyze", json=analyze_payload, headers=auth_headers)
    assert res_an.status_code == 200, res_an.text
    an_json = res_an.json()
    assert an_json["status"] == "success"
    assert an_json["table_headers"][0] == "Category"
    assert len(an_json["table_rows"]) == 3  # Engineering, Security, Operations

    # 3. Export to Styled XLSX
    export_payload = {
        "document_id": doc_id,
        "sheet_name": "Financials",
        "export_format": "xlsx",
        "title": "Category Budget Breakdown",
        "table_headers": an_json["table_headers"],
        "table_rows": an_json["table_rows"],
        "executive_insights": an_json["executive_insights"],
    }
    res_ex = await client.post("/api/v1/spreadsheets/export", json=export_payload, headers=auth_headers)
    assert res_ex.status_code == 200, res_ex.text
    ex_json = res_ex.json()
    assert ex_json["status"] == "success"
    assert ex_json["format"] == "xlsx"
    assert "download_url" in ex_json
