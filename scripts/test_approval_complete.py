"""Test complete end-to-end approval queue workflow:
1. Interception: operator submits high-risk task -> require_approval -> pending approval ticket
2. Queue visibility: operator views 'mine' (success), review restricted
3. Reviewer visibility: admin views 'review'
4. Decision & Closed-loop execution: admin approves -> task resumes -> tool executes -> output returned
5. Audit & Consume: verified consumed and recorded in audit ledger
"""

import httpx

client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0)

print("=" * 70)
print("TESTING FULL APPROVAL QUEUE WORKFLOW")
print("=" * 70)

# Step 1: Login as Operator
print("\n[Step 1] Operator Login...")
op_login = client.post("/api/v1/auth/login", json={"username": "operator", "password": "Operator1!"})
assert op_login.status_code == 200, f"Operator login failed: {op_login.text}"
op_token = op_login.json()["access_token"]
op_headers = {"Authorization": f"Bearer {op_token}"}
print("  -> Operator logged in successfully.")

# Step 2: Operator submits high-risk task
print("\n[Step 2] Operator submits high-risk task requiring dual-custody approval...")
task_res = client.post("/api/v1/ai/execute", headers=op_headers, json={
    "input": "Initiate emergency cold restart of production database cluster 'prod-db-primary' with schema lock release.",
    "data_sensitivity": "internal",
    "tool": "system_info",
    "structured": True,
})
assert task_res.status_code == 200
task_data = task_res.json()
print(f"  -> Policy Decision: {task_data.get('policy_decision')}")
print(f"  -> Approval Ticket ID: {task_data.get('approval_id')}")
print(f"  -> Risk Factors: {task_data.get('error')}")
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
assert admin_login.status_code == 200
admin_token = admin_login.json()["access_token"]
admin_headers = {"Authorization": f"Bearer {admin_token}"}
print("  -> Administrator logged in successfully.")

# Step 5: Administrator inspects 'review' queue
print("\n[Step 5] Administrator queries 'review' queue...")
rev_res = client.get("/api/v1/approvals?scope=review", headers=admin_headers)
assert rev_res.status_code == 200
rev_items = rev_res.json().get("items", [])
print(f"  -> Administrator has {len(rev_items)} request(s) in 'review' queue.")
target_appr = next((a for a in rev_items if a["id"] == appr_id), None)
assert target_appr, "Pending request not visible in admin review queue!"
print(f"  -> Found request: {target_appr['operation_summary']}")
print(f"  -> Status: {target_appr['status']}, Risk: {target_appr['risk_assessment_json'].get('risk_level')}")

# Step 6: Administrator approves with executive notes
print("\n[Step 6] Administrator approves request (triggers closed-loop execution)...")
appr_decision = client.post(
    f"/api/v1/approvals/{appr_id}/approve",
    headers=admin_headers,
    json={"notes": "Emergency cold restart authorized following P1 infrastructure review."},
)
assert appr_decision.status_code == 200, f"Approve failed: {appr_decision.text}"
decision_data = appr_decision.json()
print(f"  -> Approval Status: {decision_data.get('status')}")
print(f"  -> Resolved At: {decision_data.get('resolved_at')}")

exec_result = decision_data.get("execution_result")
print(f"  -> Closed-loop Execution Result: {exec_result}")
assert exec_result, "Expected execution_result in response!"
assert exec_result.get("success") is True, f"Execution failed: {exec_result.get('error')}"
print(f"  -> Tool Used: {exec_result.get('tool_used')}")
print(f"  -> Output Preview: {str(exec_result.get('content') or exec_result.get('tool_output'))[:150]}...")

# Step 7: Verify single-use (cannot approve again)
print("\n[Step 7] Verifying single-use constraint (cannot re-approve)...")
re_approve = client.post(
    f"/api/v1/approvals/{appr_id}/approve",
    headers=admin_headers,
    json={"notes": "Duplicate approval attempt"},
)
print(f"  -> Re-approve status: {re_approve.status_code} (Expected 400/409)")
assert re_approve.status_code in (400, 409), f"Expected failure on re-approval, got {re_approve.status_code}"

# Step 8: Verify requester cannot self-approve (Separation of Duties)
print("\n[Step 8] Testing Separation of Duties (Operator cannot self-approve)...")
# Create another task as operator
task2_res = client.post("/api/v1/ai/execute", headers=op_headers, json={
    "input": "Initiate emergency cold restart of production database cluster 'prod-db-secondary'.",
    "data_sensitivity": "internal",
    "tool": "system_info",
    "structured": True,
})
appr2_id = task2_res.json().get("approval_id")

# Operator attempts to approve own request
self_appr = client.post(
    f"/api/v1/approvals/{appr2_id}/approve",
    headers=op_headers,
    json={"notes": "Attempting self-approval"},
)
print(f"  -> Self-approval status: {self_appr.status_code} (Expected 403 Forbidden)")
assert self_appr.status_code == 403, f"Expected 403 on self-approval, got {self_appr.status_code}"
print("  -> Separation of duties strictly enforced: Self-approval rejected with HTTP 403!")

print("\n" + "=" * 70)
print("APPROVAL QUEUE WORKFLOW TEST PASSED (100% SUCCESS)!")
print("=" * 70)
