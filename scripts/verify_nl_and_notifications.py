"""Live verification script for:
1. Natural Language Data Analysis (6 analytical categories + chart specs + history)
2. Automated Notifications (event creation, unread count, read-all, preferences)
3. Role Vault Security (403 Forbidden for unauthorized vault document queries)
"""

import io

import httpx
import openpyxl

BASE_URL = "http://127.0.0.1:8000"


def create_test_workbook() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Department_Finances"

    headers = ["Department", "Month", "Budget", "Actual", "Expenditure", "Employee_Count"]
    ws.append(headers)

    data = [
        ["Infrastructure", "2026-01", 100000.0, 95000.0, 95000.0, 15],
        ["Infrastructure", "2026-02", 100000.0, 98000.0, 98000.0, 15],
        ["Security", "2026-01", 80000.0, 85000.0, 85000.0, 8],
        ["Security", "2026-02", 80000.0, 92000.0, 92000.0, 8],
        ["Engineering", "2026-01", 150000.0, 140000.0, 140000.0, 25],
        ["Engineering", "2026-02", 150000.0, 148000.0, 148000.0, 25],
        ["Finance", "2026-01", 50000.0, 48000.0, 48000.0, 6],
        ["Finance", "2026-02", 50000.0, 49000.0, 49000.0, 6],
        ["Finance", "2026-02", 50000.0, 49000.0, 49000.0, 6],  # intentional duplicate
    ]
    for row in data:
        ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def run_verification():
    client = httpx.Client(base_url=BASE_URL, timeout=60.0)

    print("=" * 70)
    print("SERVERGEN AI: VERIFYING NL ANALYTICS & NOTIFICATIONS")
    print("=" * 70)

    # 1. Login as Manager
    print("\n[Step 1] Authenticating as Department Manager...")
    login_res = client.post("/api/v1/auth/login", json={"username": "manager", "password": "Manager1!"})
    assert login_res.status_code == 200, f"Manager login failed: {login_res.text}"
    mgr_token = login_res.json()["access_token"]
    mgr_headers = {"Authorization": f"Bearer {mgr_token}"}
    print("  -> Manager authenticated successfully.")

    # 2. Upload Spreadsheet
    print("\n[Step 2] Uploading Spreadsheet to Manager Vault (Confidential)...")
    wb_bytes = create_test_workbook()
    upload_res = client.post(
        "/api/v1/spreadsheets/upload",
        headers=mgr_headers,
        data={"title": "Department Finances Q1", "classification": "confidential"},
        files={"file": ("department_finances.xlsx", wb_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert upload_res.status_code == 200, f"Upload failed: {upload_res.text}"
    upload_data = upload_res.json()
    doc_id = upload_data["document_id"]
    print(f"  -> Uploaded doc_id: {doc_id} ({upload_data['sheets_count']} sheets detected)")

    # 3. Query Schema & Suggested Questions
    print("\n[Step 3] Querying Schema & Dynamic Suggested Questions...")
    schema_res = client.get(f"/api/v1/spreadsheets/{doc_id}/schema", headers=mgr_headers)
    assert schema_res.status_code == 200, f"Schema query failed: {schema_res.text}"
    schema_data = schema_res.json()
    print(f"  -> Columns: {[c['name'] for c in schema_data['columns']]}")
    print(f"  -> Suggested Questions ({len(schema_data['suggested_questions'])}):")
    for sq in schema_data["suggested_questions"][:3]:
        print(f"     * {sq}")

    # 4. Natural Language Queries Across All 6 Categories
    queries = [
        ("1. Basic Statistical", "Calculate the total expenditure of all departments"),
        ("2. Ranking", "Show the top 3 departments based on expenditure"),
        ("3. Group-Based", "Compare expenditure across departments"),
        ("4. Financial Analysis", "Which departments exceeded their allocated budgets?"),
        ("5. Data Quality", "Find all duplicate records in this spreadsheet"),
        ("6. Trend Analysis", "Show the monthly trend for expenditure"),
    ]

    print("\n[Step 4] Executing Natural Language Queries Across 6 Analytical Categories...")
    for cat_name, q in queries:
        nl_res = client.post(
            "/api/v1/spreadsheets/nl-query",
            headers=mgr_headers,
            json={"document_id": doc_id, "question": q},
        )
        assert nl_res.status_code == 200, f"Query failed for '{q}': {nl_res.text}"
        res_data = nl_res.json()
        print(f"\n  [Category: {cat_name}]")
        print(f"  Question:  {res_data['question']}")
        print(f"  Operation: {res_data['operation']}")
        print(f"  Answer:    {res_data['answer']}")
        print(f"  Chart:     {res_data.get('chart_spec', {}).get('type')} - '{res_data.get('chart_spec', {}).get('title')}'")
        print(f"  Exec Time: {res_data['execution_time_ms']:.1f}ms")

    # 5. Check Analysis History
    print("\n[Step 5] Checking Persistent Analysis History...")
    hist_res = client.get(f"/api/v1/spreadsheets/nl-history?document_id={doc_id}", headers=mgr_headers)
    assert hist_res.status_code == 200
    hist_data = hist_res.json()
    print(f"  -> Retrieved {len(hist_data)} recorded query sessions in history.")
    assert len(hist_data) >= 6

    # 6. Verify Automated Notifications Subsystem
    print("\n[Step 6] Verifying Automated Notification Subsystem...")
    notif_res = client.get("/api/v1/notifications", headers=mgr_headers)
    assert notif_res.status_code == 200
    notifs_payload = notif_res.json()
    notifs = notifs_payload.get("items", notifs_payload) if isinstance(notifs_payload, dict) else notifs_payload
    print(f"  -> Current manager notifications: {len(notifs)}")
    for n in notifs[:3]:
        print(f"     [{n['category'].upper()}] {n['title']} (read={n['is_read']})")

    unread_res = client.get("/api/v1/notifications/unread-count", headers=mgr_headers)
    assert unread_res.status_code == 200
    print(f"  -> Unread count: {unread_res.json()['unread_count']}")

    # Mark all read
    read_all_res = client.post("/api/v1/notifications/read-all", headers=mgr_headers)
    assert read_all_res.status_code == 200
    print(f"  -> Mark all read: {read_all_res.json().get('marked_read', 0)} marked read.")

    unread_after = client.get("/api/v1/notifications/unread-count", headers=mgr_headers).json()["unread_count"]
    assert unread_after == 0
    print("  -> Unread count verified 0.")

    # Notification preferences
    pref_res = client.get("/api/v1/notifications/preferences", headers=mgr_headers)
    assert pref_res.status_code == 200
    print(f"  -> Preferences loaded: approvals={pref_res.json()['approvals_enabled']}, analytics={pref_res.json()['analytics_enabled']}")

    # 7. Verify Role Vault Clearance & Zero-Trust RBAC Isolation
    print("\n[Step 7] Verifying Role Vault Security Isolation (Zero-Trust RBAC)...")
    emp_login = client.post("/api/v1/auth/login", json={"username": "employee", "password": "Employee1!"})
    assert emp_login.status_code == 200
    emp_token = emp_login.json()["access_token"]
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # Employee tries to query manager's confidential document
    emp_nl_res = client.post(
        "/api/v1/spreadsheets/nl-query",
        headers=emp_headers,
        json={"document_id": doc_id, "question": "Calculate total expenditure"},
    )
    print(f"  -> Employee querying confidential document returned HTTP {emp_nl_res.status_code}")
    assert emp_nl_res.status_code == 403, f"Expected 403 Forbidden, got {emp_nl_res.status_code}"
    print("  -> RBAC security boundary confirmed: Unauthorized access correctly rejected with HTTP 403!")

    print("\n" + "=" * 70)
    print("ALL VERIFICATIONS COMPLETED SUCCESSFULLY (100% PASS)!")
    print("=" * 70)


if __name__ == "__main__":
    run_verification()
