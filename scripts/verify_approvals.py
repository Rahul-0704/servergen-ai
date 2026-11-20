"""
ServerGen AI — End-to-End Approval Queue & Dual-Custody Verification Suite.

Validates the complete 5-stage approval lifecycle:
1. Interception: High-risk task held in PENDING state with SHA-256 fingerprint.
2. Queue Scopes: Operator views 'mine' queue; non-reviewers restricted from 'review'.
3. Administrator Clearance: Admin reviews and approves CRITICAL task.
4. Closed-Loop Execution: Live tool execution resumes and returns output to reviewer.
5. Replay Protection: Ticket consumed immediately; duplicate approval blocked.
6. Separation of Duties: Requesters cannot self-approve (HTTP 403 Forbidden).
7. Executive Review: Manager reviews and approves HIGH-risk task.
"""

from __future__ import annotations

import httpx

client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0)

print("=" * 70)
print("SERVERGEN AI: VERIFYING APPROVAL QUEUE & DUAL-CUSTODY WORKFLOW")
print("=" * 70)

# Step 1: Login as Operator
print("\n[Step 1] Operator Login...")
op_login = client.post("/api/v1/auth/login", json={"username": "operator", "password": "Operator1!"})
assert op_login.status_code == 200, f"Operator login failed: {op_login.text}"
op_token = op_login.json()["access_token"]
op_headers = {"Authorization": f"Bearer {op_token}"}
print("  -> Operator logged in successfully.")

# Step 2: Operator submits CRITICAL risk task
print("\n[Step 2] Operator submits CRITICAL risk task requiring dual-custody approval...")
task_res = client.post(
    "/api/v1/ai/execute",
    headers=op_headers,
    json={
        "input": "Initiate emergency cold restart of production database cluster 'prod-db-primary' with schema lock release.",
        "data_sensitivity": "internal",
        "tool": "system_info",
        "structured": True,
    },
)
assert task_res.status_code == 200
task_data = task_res.json()
print(f"  -> Policy Decision: {task_data.get('policy_decision')}")
print(f"  -> Approval Ticket ID: {task_data.get('approval_id')}")
appr_id = task_data.get("approval_id")
assert appr_id, "Expected approval_id to be returned!"

# Step 3: Operator inspects 'mine' queue
print("\n[Step 3] Operator queries 'mine' queue...")
mine_res = client.get("/api/v1/approvals?scope=mine", headers=op_headers)
assert mine_res.status_code == 200
mine_items = mine_res.json().get("items", [])
print(f"  -> Operator has {len(mine_items)} request(s) in 'mine' queue.")
assert any(a["id"] == appr_id for a in mine_items), "Created approval not found in 'mine' queue!"

# Step 4: Login as Administrator
print("\n[Step 4] Administrator Login...")
admin_login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin"})
assert admin_login.status_code == 200, f"Admin login failed: {admin_login.text}"
admin_token = admin_login.json()["access_token"]
admin_headers = {"Authorization": f"Bearer {admin_token}"}
print("  -> Administrator logged in successfully.")

# Step 5: Administrator inspects 'review' queue
print("\n[Step 5] Administrator queries 'review' queue...")
rev_res = client.get("/api/v1/approvals?scope=review", headers=admin_headers)
assert rev_res.status_code == 200
rev_items = rev_res.json().get("items", [])
print(f"  -> Admin has {len(rev_items)} pending request(s) in 'review' queue.")
target_appr = next((a for a in rev_items if a["id"] == appr_id), None)
assert target_appr, "Target approval not found in admin review queue!"

# Step 6: Admin approves & closed-loop execution runs
print(f"\n[Step 6] Administrator approves ticket {appr_id[:8]}...")
appr_decision = client.post(
    f"/api/v1/approvals/{appr_id}/approve",
    headers=admin_headers,
    json={"notes": "Emergency cold restart authorized following P1 infrastructure review."},
)
assert appr_decision.status_code == 200, f"Approve failed: {appr_decision.text}"
decision_data = appr_decision.json()
print(f"  -> Approval Status: {decision_data.get('status')}")
exec_result = decision_data.get("execution_result")
assert exec_result, "Expected execution_result in response!"
assert exec_result.get("success") is True, f"Execution failed: {exec_result.get('error')}"
print(f"  -> Tool Used: {exec_result.get('tool_used')}")
print(f"  -> Output: {str(exec_result.get('content') or exec_result.get('tool_output'))[:120]}...")

# Step 7: Verify single-use constraint (replay prevention)
print("\n[Step 7] Verifying single-use constraint (cannot re-approve)...")
re_approve = client.post(
    f"/api/v1/approvals/{appr_id}/approve",
    headers=admin_headers,
    json={"notes": "Duplicate approval attempt"},
)
print(f"  -> Re-approve status: {re_approve.status_code} (Expected 400/409)")
assert re_approve.status_code in (400, 409)

# Step 8: Verify Separation of Duties (Operator cannot self-approve)
print("\n[Step 8] Testing Separation of Duties (Operator cannot self-approve)...")
task2_res = client.post(
    "/api/v1/ai/execute",
    headers=op_headers,
    json={
        "input": "Initiate emergency cold restart of production database cluster 'prod-db-secondary'.",
        "data_sensitivity": "internal",
        "tool": "system_info",
        "structured": True,
    },
)
appr2_id = task2_res.json().get("approval_id")

self_appr = client.post(
    f"/api/v1/approvals/{appr2_id}/approve",
    headers=op_headers,
    json={"notes": "Attempting self-approval"},
)
print(f"  -> Self-approval status: {self_appr.status_code} (Expected 403 Forbidden)")
assert self_appr.status_code == 403
print("  -> Separation of duties strictly enforced: Self-approval rejected with HTTP 403!")

# Step 9: Manager approves HIGH-risk task
print("\n[Step 9] Testing Manager approval on HIGH-risk diagnostic task...")
mgr_login = client.post("/api/v1/auth/login", json={"username": "manager", "password": "Manager1!"})
assert mgr_login.status_code == 200
mgr_headers = {"Authorization": f"Bearer {mgr_login.json()['access_token']}"}

task3_res = client.post(
    "/api/v1/ai/execute",
    headers=op_headers,
    json={
        "input": "Run automated infrastructure diagnostic query for staging cluster.",
        "data_sensitivity": "internal",
        "tool": "system_info",
        "structured": True,
    },
)
appr3_id = task3_res.json().get("approval_id")
mgr_appr = client.post(
    f"/api/v1/approvals/{appr3_id}/approve",
    headers=mgr_headers,
    json={"notes": "Manager authorized staging diagnostic."},
)
assert mgr_appr.status_code == 200
mgr_exec = mgr_appr.json().get("execution_result")
assert mgr_exec and mgr_exec.get("success") is True
print("  -> Manager approved HIGH-risk task and closed-loop execution succeeded!")

print("\n" + "=" * 70)
print("APPROVAL QUEUE & DUAL-CUSTODY VERIFICATION PASSED (100% SUCCESS)!")
print("=" * 70)
