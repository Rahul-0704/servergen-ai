"""
ServerGen AI — Natural Language Data Analysis Test Suite.

Verifies:
1. Safe Intent Parser (Statistical, Ranking, Group-By, Financial, Quality, Trend)
2. Deterministic exact numerical precision with Pandas / NumPy
3. Top N and Bottom N ranking algorithms
4. Financial analysis (Budget vs Actual variance and overrun detection)
5. Data quality analysis (Missing values, duplicates, IQR outliers)
6. Empty and invalid dataset resilience
7. Role-vault clearance checks (employee blocked from manager confidential sheet)
8. End-to-end REST API (/api/v1/spreadsheets/nl-query, /schema, /nl-history)
"""

from __future__ import annotations

import io
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.app import create_app
from src.auth.permissions import PermissionCode
from src.auth.rbac import AuthContext
from src.core.database import get_db
from src.core.security import create_access_token, hash_password
from src.models.role import Role
from src.models.user import User
from src.rag.service import DocumentService
from src.services.nl_analytics_service import NLAnalyticsService
from src.services.spreadsheet_service import SheetData, SpreadsheetAnalyticsService


def _create_sample_sheet(
    headers: list[str], rows: list[list[any]], name: str = "Financials"
) -> SheetData:
    """Helper to build a typed SheetData structure."""
    svc = SpreadsheetAnalyticsService()
    wb = Workbook()
    ws = wb.active
    ws.title = name
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    wb_data = svc.parse_content(buf.getvalue(), f"{name}.xlsx")
    return wb_data.sheets[name]


def test_nl_intent_parsing():
    """Verify that user questions map deterministically to valid analytical operations."""
    headers = ["Department", "Month", "Budget", "Actual_Expense", "Revenue", "Profit"]
    rows = [
        ["Engineering", "Jan", 50000, 52000, 80000, 28000],
        ["Marketing", "Jan", 30000, 28000, 45000, 17000],
        ["Sales", "Jan", 40000, 41000, 90000, 49000],
    ]
    sheet = _create_sample_sheet(headers, rows)
    nl_svc = NLAnalyticsService()

    # 1. Basic Stats
    p1 = nl_svc.parse_intent("Calculate the total expenditure of all departments", sheet)
    assert p1.operation == "statistical"
    assert p1.sub_operation == "sum"

    p1_avg = nl_svc.parse_intent("Calculate the average revenue", sheet)
    assert p1_avg.operation == "statistical"
    assert p1_avg.sub_operation == "avg"

    p_grp = nl_svc.parse_intent("Compare average revenue across departments", sheet)
    assert p_grp.operation == "groupby"
    assert p_grp.sub_operation == "avg"

    # 2. Ranking
    p2 = nl_svc.parse_intent("Show the top 5 departments based on expenditure", sheet)
    assert p2.operation == "ranking"
    assert p2.sub_operation == "top_n"
    assert p2.n_records == 5

    p2_highest = nl_svc.parse_intent("Which department has the highest expenses?", sheet)
    assert p2_highest.operation == "ranking"
    assert p2_highest.n_records == 1

    # 3. Financial Variance
    p3 = nl_svc.parse_intent("Which departments exceeded their allocated budgets?", sheet)
    assert p3.operation == "financial"
    assert p3.sub_operation == "budget_vs_actual"

    # 4. Data Quality
    p4_dup = nl_svc.parse_intent("Find all duplicate transactions in this spreadsheet", sheet)
    assert p4_dup.operation == "quality"
    assert p4_dup.sub_operation == "duplicates"

    p4_null = nl_svc.parse_intent("Check for missing values in Budget", sheet)
    assert p4_null.operation == "quality"
    assert p4_null.sub_operation == "missing_values"

    p4_outlier = nl_svc.parse_intent("Detect unusual outlier expenses", sheet)
    assert p4_outlier.operation == "quality"
    assert p4_outlier.sub_operation == "outliers"

    # 5. Trend
    p5 = nl_svc.parse_intent("Show monthly revenue trend for 2026", sheet)
    assert p5.operation == "trend"
    assert p5.sub_operation == "time_series"


def test_nl_deterministic_numerical_precision():
    """Verify that calculations execute with exact Python/Pandas math, not LLM estimates."""
    headers = ["Department", "Expense"]
    rows = [
        ["HR", 12500.50],
        ["IT", 37400.25],
        ["Finance", 15099.25],
    ]
    sheet = _create_sample_sheet(headers, rows)
    nl_svc = NLAnalyticsService()

    plan = nl_svc.parse_intent("Calculate total expense", sheet)
    res = nl_svc.execute_plan(sheet, plan)

    expected_total = 12500.50 + 37400.25 + 15099.25  # 65000.00
    assert res["metrics"]["calculated_value"] == expected_total
    assert "65,000.00" in res["direct_answer"]


def test_nl_top_and_bottom_ranking():
    """Verify top N and bottom N ranking algorithms."""
    headers = ["Department", "Spending"]
    rows = [
        ["Legal", 5000],
        ["Sales", 45000],
        ["Engineering", 80000],
        ["HR", 12000],
    ]
    sheet = _create_sample_sheet(headers, rows)
    nl_svc = NLAnalyticsService()

    # Top 2
    plan_top = nl_svc.parse_intent("Top 2 departments by spending", sheet)
    res_top = nl_svc.execute_plan(sheet, plan_top)
    assert res_top["metrics"]["leading_entity"] == "Engineering"
    assert len(res_top["table_rows"]) == 2
    assert res_top["table_rows"][0][0] == "Engineering"
    assert res_top["table_rows"][1][0] == "Sales"

    # Lowest
    plan_bot = nl_svc.parse_intent("Which department has the lowest spending?", sheet)
    res_bot = nl_svc.execute_plan(sheet, plan_bot)
    assert res_bot["metrics"]["leading_entity"] == "Legal"
    assert res_bot["table_rows"][0][0] == "Legal"


def test_nl_financial_budget_variance_and_overruns():
    """Verify budget vs actual variance calculations and over-budget identification."""
    headers = ["Department", "Budget", "Actual_Expense"]
    rows = [
        ["Operations", 50000, 55000],  # Overrun by 5,000
        ["Security", 20000, 18000],  # Under by 2,000
        ["Facilities", 10000, 14000],  # Overrun by 4,000
    ]
    sheet = _create_sample_sheet(headers, rows)
    nl_svc = NLAnalyticsService()

    plan = nl_svc.parse_intent("Which departments exceeded budget?", sheet)
    res = nl_svc.execute_plan(sheet, plan)

    assert res["metrics"]["over_budget_count"] == 2
    assert "Operations" in res["direct_answer"]
    assert "Facilities" in res["direct_answer"]
    assert "Security" not in res["direct_answer"].split("exceeded their allocated budgets:")[1]


def test_nl_data_quality_duplicates_and_missing():
    """Verify exact duplicate detection and missing values analysis."""
    headers = ["ID", "Category", "Amount"]
    rows = [
        [101, "Hardware", 250],
        [102, "Software", 500],
        [101, "Hardware", 250],  # Duplicate
        [103, "Cloud", None],  # Missing Amount
    ]
    sheet = _create_sample_sheet(headers, rows)
    nl_svc = NLAnalyticsService()

    # Duplicates
    plan_dup = nl_svc.parse_intent("Find duplicate records", sheet)
    res_dup = nl_svc.execute_plan(sheet, plan_dup)
    assert res_dup["metrics"]["duplicate_count"] == 1

    # Missing values
    plan_null = nl_svc.parse_intent("Show missing values", sheet)
    res_null = nl_svc.execute_plan(sheet, plan_null)
    assert res_null["metrics"]["total_missing"] >= 1


def test_nl_outlier_detection_iqr():
    """Verify statistical outlier detection using Interquartile Range."""
    headers = ["Transaction_ID", "Amount"]
    rows = [
        [1, 100],
        [2, 105],
        [3, 110],
        [4, 98],
        [5, 102],
        [6, 99],
        [7, 50000],  # Extreme outlier
    ]
    sheet = _create_sample_sheet(headers, rows)
    nl_svc = NLAnalyticsService()

    plan = nl_svc.parse_intent("Find outlier transactions", sheet)
    res = nl_svc.execute_plan(sheet, plan)

    assert res["metrics"]["outlier_count"] == 1
    assert 50000.0 in [r[1] for r in res["table_rows"]]


def test_nl_empty_dataset_resilience():
    """Verify that empty datasets are handled gracefully without raising exceptions."""
    sheet = SheetData(name="Empty", headers=["Col1", "Col2"], rows=[])
    nl_svc = NLAnalyticsService()

    plan = nl_svc.parse_intent("What is the average?", sheet)
    res = nl_svc.execute_plan(sheet, plan)

    assert "contains no data rows" in res["direct_answer"]
    assert res["table_rows"] == []


@pytest.mark.anyio
async def test_nl_api_lifecycle_and_role_vault_clearance(db_session: AsyncSession):
    """
    Verify the full FastAPI endpoint lifecycle:
    1. Upload spreadsheet into Company-Wide Library ('all' vault)
    2. Upload confidential spreadsheet into Manager Vault ('manager' vault)
    3. Query 'all' spreadsheet via POST /api/v1/spreadsheets/nl-query as employee -> SUCCESS
    4. Query 'manager' spreadsheet as employee -> 403 FORBIDDEN
    5. Query 'manager' spreadsheet as manager -> SUCCESS
    6. Fetch schema and history endpoints
    """
    app = create_app()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # 1. Setup Manager and Employee test users
    role_mgr = (
        await db_session.execute(select(Role).where(Role.name == "manager"))
    ).scalar_one_or_none()
    if not role_mgr:
        role_mgr = Role(id=uuid.uuid4(), name="manager", description="Manager", permissions=[])
        db_session.add(role_mgr)

    role_emp = (
        await db_session.execute(select(Role).where(Role.name == "general_employee"))
    ).scalar_one_or_none()
    if not role_emp:
        role_emp = Role(
            id=uuid.uuid4(), name="general_employee", description="Employee", permissions=[]
        )
        db_session.add(role_emp)
    await db_session.flush()

    user_mgr = User(
        id=uuid.uuid4(),
        username=f"mgr_{uuid.uuid4().hex[:6]}",
        email=f"mgr_{uuid.uuid4().hex[:6]}@enterprise.local",
        hashed_password=hash_password("Pass1!"),
        role_id=role_mgr.id,
        is_active=True,
    )
    user_emp = User(
        id=uuid.uuid4(),
        username=f"emp_{uuid.uuid4().hex[:6]}",
        email=f"emp_{uuid.uuid4().hex[:6]}@enterprise.local",
        hashed_password=hash_password("Pass1!"),
        role_id=role_emp.id,
        is_active=True,
    )
    db_session.add_all([user_mgr, user_emp])
    await db_session.commit()

    token_mgr = create_access_token(user_id=str(user_mgr.id), role="manager")
    token_emp = create_access_token(user_id=str(user_emp.id), role="general_employee")

    # 2. Ingest two documents using DocumentService
    doc_service = DocumentService(db_session)
    auth_mgr = AuthContext(
        user_id=str(user_mgr.id),
        role="manager",
        permissions={
            PermissionCode.DOCUMENT_UPLOAD.value,
            PermissionCode.DOCUMENT_READ.value,
            PermissionCode.AI_EXECUTE.value,
        },
    )

    # General spreadsheet (Company-wide)
    wb_gen = Workbook()
    ws_g = wb_gen.active
    ws_g.title = "SalesData"
    ws_g.append(["Region", "Revenue"])
    ws_g.append(["North", 15000])
    ws_g.append(["South", 25000])
    buf_g = io.BytesIO()
    wb_gen.save(buf_g)

    doc_gen, _, _ = await doc_service.create_document_with_file(
        auth=auth_mgr,
        filename="sales_2026.xlsx",
        content=buf_g.getvalue(),
        title="Company Sales 2026",
        vault_scope="all",
        classification="internal",
        auto_index=False,
    )

    # Confidential spreadsheet (Manager vault)
    wb_conf = Workbook()
    ws_c = wb_conf.active
    ws_c.title = "ExecutiveCompensation"
    ws_c.append(["Executive", "Salary", "Bonus"])
    ws_c.append(["CEO", 450000, 200000])
    ws_c.append(["CFO", 350000, 150000])
    buf_c = io.BytesIO()
    wb_conf.save(buf_c)

    doc_conf, _, _ = await doc_service.create_document_with_file(
        auth=auth_mgr,
        filename="executive_comp.xlsx",
        content=buf_c.getvalue(),
        title="Executive Compensation 2026",
        vault_scope="manager",
        classification="restricted",
        auto_index=False,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test 1: Employee queries public spreadsheet -> SUCCESS
        res1 = await client.post(
            "/api/v1/spreadsheets/nl-query",
            headers={"Authorization": f"Bearer {token_emp}"},
            json={
                "document_id": str(doc_gen.id),
                "question": "What is the total revenue?",
            },
        )
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["status"] == "success"
        assert "40,000.00" in data1["direct_answer"]
        assert len(data1["table_rows"]) >= 1

        # Test 2: Employee queries manager confidential spreadsheet -> 403 FORBIDDEN
        res2 = await client.post(
            "/api/v1/spreadsheets/nl-query",
            headers={"Authorization": f"Bearer {token_emp}"},
            json={
                "document_id": str(doc_conf.id),
                "question": "Show CEO salary",
            },
        )
        assert res2.status_code == 403
        assert "Manager Confidential Vault" in res2.json()["detail"]

        # Test 3: Manager queries confidential spreadsheet -> 200 SUCCESS
        res3 = await client.post(
            "/api/v1/spreadsheets/nl-query",
            headers={"Authorization": f"Bearer {token_mgr}"},
            json={
                "document_id": str(doc_conf.id),
                "question": "What is the total salary?",
            },
        )
        assert res3.status_code == 200
        data3 = res3.json()
        assert data3["status"] == "success"
        assert "800,000.00" in data3["direct_answer"]

        # Test 4: Schema exploration endpoint
        res_schema = await client.get(
            f"/api/v1/spreadsheets/{doc_gen.id}/schema",
            headers={"Authorization": f"Bearer {token_emp}"},
        )
        assert res_schema.status_code == 200
        schema_data = res_schema.json()
        assert schema_data["active_sheet"] == "SalesData"
        assert len(schema_data["columns"]) == 2
        assert len(schema_data["suggested_questions"]) >= 2

        # Test 5: Analysis History endpoint
        res_hist = await client.get(
            "/api/v1/spreadsheets/nl-history",
            headers={"Authorization": f"Bearer {token_emp}"},
        )
        assert res_hist.status_code == 200
        hist_data = res_hist.json()
        assert len(hist_data) >= 1
        assert "total revenue" in hist_data[0]["question"].lower()
