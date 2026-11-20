"""Test Manager dual-custody approval on HIGH risk task:
1. Operator submits HIGH-risk task
2. Manager reviews and approves
3. Verify closed loop execution under manager authorization
"""

import httpx

client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0)

print("=" * 70)
print("TESTING MANAGER APPROVAL ON HIGH-RISK TASK")
print("=" * 70)

# Operator login
op_login = client.post("/api/v1/auth/login", json={"username": "operator", "password": "Operator1!"})
assert op_login.status_code == 200
op_headers = {"Authorization": f"Bearer {op_login.json()['access_token']}"}

# Submit HIGH-risk task (e.g. system_info with internal sensitivity and execute action, non-production)
task_res = client.post("/api/v1/ai/execute", headers=op_headers, json={
    "input": "Run automated infrastructure diagnostic query for staging cluster.",
    "data_sensitivity": "internal",
    "tool": "system_info",
    "structured": True,
})
assert task_res.status_code == 200
task_data = task_res.json()
print(f"Policy Decision: {task_data.get('policy_decision')}")
print(f"Approval ID: {task_data.get('approval_id')}")
appr_id = task_data.get("approval_id")

if appr_id:
    # Manager login
    mgr_login = client.post("/api/v1/auth/login", json={"username": "manager", "password": "Manager1!"})
    assert mgr_login.status_code == 200
    mgr_headers = {"Authorization": f"Bearer {mgr_login.json()['access_token']}"}

    # Manager approves via /api/v1/approvals/{id}/approve
    appr_res = client.post(
        f"/api/v1/approvals/{appr_id}/approve",
        headers=mgr_headers,
        json={"notes": "Manager approved staging diagnostic."},
    )
    print(f"Manager Approve Status: {appr_res.status_code}")
    res_data = appr_res.json()
    print(f"Approval Status: {res_data.get('status')}")
    exec_res = res_data.get("execution_result")
    print(f"Execution Success: {exec_res.get('success') if exec_res else None}")
    if exec_res and exec_res.get("success"):
        print(f"Tool Output: {exec_res.get('tool_output')}")
        print("MANAGER APPROVAL WORKED 100%!")

print("=" * 70)
