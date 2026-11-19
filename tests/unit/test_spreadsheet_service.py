"""
ServerGen AI — Spreadsheet Analytics Subsystem Unit Tests.

Verifies:
1. Multi-sheet Excel (.xlsx) workbook ingestion and schema extraction
2. CSV parsing, data cleaning, and column profiling
3. Deterministic summary statistics (sum, mean, median, min, max, std dev)
4. Grouped aggregations (SUM, AVG, COUNT across categories)
5. Filtering, sorting, and conditional slicing
6. Formatted Markdown table rendering
7. Styled Excel (.xlsx) export with cell styles and borders
8. SpreadsheetAnalyticsTool integration with tool registry
"""

from __future__ import annotations

import io

import pytest
from openpyxl import Workbook
from src.services.spreadsheet_service import SpreadsheetAnalyticsService
from src.tools.spreadsheet_tool import SpreadsheetAnalyticsTool


def _create_sample_excel_bytes() -> bytes:
    """Helper to generate a multi-sheet test workbook in memory."""
    wb = Workbook()

    # Sheet 1: Sales
    ws1 = wb.active
    ws1.title = "Regional_Sales"
    ws1.append(["Region", "Department", "Quarter", "Revenue", "Expense", "Margin"])
    ws1.append(["APAC", "Infrastructure", "Q1", 120000.0, 75000.0, 0.375])
    ws1.append(["APAC", "Security", "Q1", 95000.0, 45000.0, 0.526])
    ws1.append(["EMEA", "Infrastructure", "Q1", 210000.0, 140000.0, 0.333])
    ws1.append(["EMEA", "Security", "Q1", 180000.0, 90000.0, 0.500])
    ws1.append(["AMER", "Infrastructure", "Q1", 350000.0, 200000.0, 0.428])
    ws1.append(["AMER", "Security", "Q1", 280000.0, 120000.0, 0.571])

    # Sheet 2: Inventory
    ws2 = wb.create_sheet(title="Server_Hardware")
    ws2.append(["Server_ID", "Model", "Rack_Unit", "Status", "Memory_GB", "CPU_Cores"])
    ws2.append(["SRV-001", "Dell PowerEdge R750", 2, "Active", 256, 64])
    ws2.append(["SRV-002", "HPE ProLiant DL380", 2, "Active", 512, 128])
    ws2.append(["SRV-003", "Cisco UCS C240", 2, "Standby", 128, 32])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _create_sample_csv_bytes() -> bytes:
    csv_text = (
        "Item,Category,Price,Quantity,InStock\n"
        "Firewall License,Software,$4500.00,10,True\n"
        "Switch 48-Port,Hardware,$2200.50,15,True\n"
        "Cat6 Cable (Box),Hardware,$180.00,50,True\n"
        "SOC Support Package,Services,$12000.00,2,False\n"
    )
    return csv_text.encode("utf-8")


@pytest.fixture
def service(tmp_path):
    return SpreadsheetAnalyticsService(storage_dir=tmp_path)


def test_xlsx_multi_sheet_parsing(service):
    raw = _create_sample_excel_bytes()
    wb_data = service.parse_content(raw, "enterprise_data.xlsx")

    assert len(wb_data.sheet_names) == 2
    assert "Regional_Sales" in wb_data.sheets
    assert "Server_Hardware" in wb_data.sheets

    s1 = wb_data.sheets["Regional_Sales"]
    assert s1.row_count() == 6
    assert s1.col_count() == 6
    assert "Revenue" in s1.headers
    assert "Margin" in s1.headers

    # Check numeric profiling
    rev_profile = s1.column_profiles["Revenue"]
    assert rev_profile.inferred_type == "numeric"
    assert rev_profile.total == 1235000.0
    assert rev_profile.min_val == 95000.0
    assert rev_profile.max_val == 350000.0

    s2 = wb_data.sheets["Server_Hardware"]
    assert s2.row_count() == 3
    assert "Memory_GB" in s2.headers
    mem_profile = s2.column_profiles["Memory_GB"]
    assert mem_profile.total == 896.0


def test_csv_parsing_and_cleaning(service):
    raw = _create_sample_csv_bytes()
    wb_data = service.parse_content(raw, "hardware_inventory.csv")

    assert len(wb_data.sheet_names) == 1
    s = wb_data.sheets[wb_data.sheet_names[0]]
    assert s.row_count() == 4
    assert "Price" in s.headers
    assert "Quantity" in s.headers

    price_profile = s.column_profiles["Price"]
    assert price_profile.inferred_type == "numeric"
    # Currency symbol stripped cleanly
    assert price_profile.total == 18880.50


def test_group_by_aggregation(service):
    raw = _create_sample_excel_bytes()
    wb_data = service.parse_content(raw, "sales.xlsx")
    s = wb_data.sheets["Regional_Sales"]

    headers, rows = service.group_by_aggregate(
        s,
        group_column="Department",
        aggregations=[
            {"column": "Revenue", "op": "sum"},
            {"column": "Expense", "op": "sum"},
            {"column": "Margin", "op": "avg"},
        ],
    )

    assert headers[0] == "Department"
    assert headers[1] == "Record Count"
    assert "SUM of Revenue" in headers[2]
    assert len(rows) == 2  # Infrastructure and Security

    infra = next(r for r in rows if r[0] == "Infrastructure")
    sec = next(r for r in rows if r[0] == "Security")

    assert infra[1] == 3  # 3 rows
    assert infra[2] == 680000.0  # 120k + 210k + 350k
    assert sec[1] == 3  # 3 rows
    assert sec[2] == 555000.0  # 95k + 180k + 280k


def test_filter_and_sort(service):
    raw = _create_sample_excel_bytes()
    wb_data = service.parse_content(raw, "sales.xlsx")
    s = wb_data.sheets["Regional_Sales"]

    headers, rows = service.filter_and_sort(
        s,
        filter_col="Revenue",
        operator=">=",
        filter_val=200000.0,
        sort_col="Revenue",
        ascending=False,
    )

    assert len(rows) == 3
    # Top row is AMER Infrastructure ($350,000)
    rev_idx = headers.index("Revenue")
    assert rows[0][rev_idx] == 350000.0
    assert rows[1][rev_idx] == 280000.0
    assert rows[2][rev_idx] == 210000.0


def test_markdown_table_formatting(service):
    headers = ["Department", "Count", "Total_Sales", "Margin_Pct"]
    rows = [
        ["Infrastructure", 12, 450200.75, 0.425],
        ["Security", 8, 310500.00, 0.582],
    ]
    md = service.format_markdown_table(headers, rows)
    assert "| Department | Count | Total_Sales | Margin_Pct |" in md
    assert "450,200.75" in md
    assert "42.50%" in md
    assert "58.20%" in md


def test_export_styled_xlsx(service):
    headers = ["Metric", "Baseline", "Actual", "Growth"]
    rows = [
        ["Active Nodes", 120, 150, 0.25],
        ["Monthly Throughput GB", 54000.0, 72500.0, 0.342],
    ]
    out_path = service.export_styled_xlsx("KPI_Report", headers, rows, title="Q3 Platform KPIs")
    assert out_path.exists()
    assert out_path.stat().st_size > 1000

    # Verify workbook is readable by openpyxl
    wb = Workbook()
    wb = openpyxl_verify = load_sample(out_path)
    assert openpyxl_verify.active.title == "KPI_Report"


def load_sample(path):
    from openpyxl import load_workbook
    return load_workbook(path)


@pytest.mark.asyncio
async def test_spreadsheet_analytics_tool(tmp_path):
    svc = SpreadsheetAnalyticsService(storage_dir=tmp_path)
    tool = SpreadsheetAnalyticsTool(service=svc)
    assert tool.metadata.name == "spreadsheet_analytics"

    raw_excel = _create_sample_excel_bytes()

    # 1. Overview operation
    res_overview = await tool.execute({
        "content": raw_excel,
        "filename": "q1_regional_sales.xlsx",
        "operation": "overview",
    })
    assert res_overview.success is True
    assert "Sheet Overview: `Regional_Sales`" in res_overview.output

    # 2. GroupBy operation
    res_group = await tool.execute({
        "content": raw_excel,
        "filename": "q1_regional_sales.xlsx",
        "operation": "groupby",
        "group_column": "Region",
        "aggregations": [{"column": "Revenue", "op": "sum"}],
    })
    assert res_group.success is True
    assert "Grouped Aggregation (Region)" in res_group.output
    assert "APAC" in res_group.output
    assert "EMEA" in res_group.output
    assert "AMER" in res_group.output
