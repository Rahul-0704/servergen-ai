"""Quick smoke test — all 5 roles + security pipeline."""
import httpx

BASE = "http://127.0.0.1:8000"

USERS = [
    ("admin",    "admin",      "administrator"),
    ("operator", "Operator1!", "it_operator"),
    ("analyst",  "Analyst1!",  "security_analyst"),
    ("manager",  "Manager1!",  "manager"),
    ("employee", "Employee1!", "general_employee"),
]


def main():
    print("=" * 60)
    print("  ServerGen AI - Smoke Test (All Roles)")
    print("=" * 60)

    # 1. Health
    r = httpx.get(f"{BASE}/health")
    print(f"\n[Health] {r.status_code} - {r.json()['status']}")

    # 2. Login each user and check profile
    print("\n--- Login & Profile ---")
    tokens = {}
    for user, pwd, role in USERS:
        r = httpx.post(f"{BASE}/api/v1/auth/login", json={"username": user, "password": pwd})
        if r.status_code == 200:
            tokens[user] = r.json()["access_token"]
            # Get profile
            p = httpx.get(f"{BASE}/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens[user]}"})
            prof = p.json()
            print(f"  [OK] {user:<10} role={prof.get('role','?'):<20} login=200 profile=200")
        else:
            print(f"  [FAIL] {user:<10} login={r.status_code}")

    # 3. AI Execute as admin (low risk)
    print("\n--- AI Execute (admin, PUBLIC) ---")
    r = httpx.post(f"{BASE}/api/v1/ai/execute",
        json={"input": "What is 2+2?", "data_sensitivity": "public"},
        headers={"Authorization": f"Bearer {tokens['admin']}"})
    d = r.json()
    print(f"  Category={d.get('task_category')} Risk={d.get('risk_level')} Policy={d.get('policy_decision')}")

    # 4. Calculator tool
    print("\n--- Calculator Tool ---")
    r = httpx.post(f"{BASE}/api/v1/ai/execute",
        json={"input": "calc", "tool": "calculator", "tool_parameters": {"expression": "2+2*10"}, "data_sensitivity": "public"},
        headers={"Authorization": f"Bearer {tokens['admin']}"})
    d = r.json()
    print(f"  Tool={d.get('tool_used')} Output={d.get('tool_output')} Success={d.get('success')}")

    # 5. Unknown tool (should DENY)
    print("\n--- Unknown Tool (should DENY) ---")
    r = httpx.post(f"{BASE}/api/v1/ai/execute",
        json={"input": "hack", "tool": "nonexistent", "data_sensitivity": "public"},
        headers={"Authorization": f"Bearer {tokens['admin']}"})
    d = r.json()
    print(f"  Policy={d.get('policy_decision')} Error={d.get('error','')[:60]}")

    # 6. RBAC test: each role tries RESTRICTED data
    print("\n--- RESTRICTED Data Access (per role) ---")
    for user, _, role in USERS:
        if user not in tokens:
            continue
        r = httpx.post(f"{BASE}/api/v1/ai/execute",
            json={"input": "Read classified data", "data_sensitivity": "restricted"},
            headers={"Authorization": f"Bearer {tokens[user]}"})
        d = r.json()
        policy = d.get("policy_decision", "?")
        appr = d.get("approval_id", "")
        err = d.get("error", "")[:50]
        print(f"  {user:<10} ({role:<18}) -> {policy:<18} {('approval='+appr[:8]+'..') if appr else err}")

    # 7. CONFIDENTIAL data test
    print("\n--- CONFIDENTIAL Data Access (per role) ---")
    for user, _, role in USERS:
        if user not in tokens:
            continue
        r = httpx.post(f"{BASE}/api/v1/ai/execute",
            json={"input": "Read HR records", "data_sensitivity": "confidential"},
            headers={"Authorization": f"Bearer {tokens[user]}"})
        d = r.json()
        policy = d.get("policy_decision", "?")
        print(f"  {user:<10} ({role:<18}) -> {policy}")

    # 8. Audit events (admin)
    print("\n--- Audit Events ---")
    r = httpx.get(f"{BASE}/api/v1/audit/events?limit=3",
        headers={"Authorization": f"Bearer {tokens['admin']}"})
    data = r.json()
    items = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    print(f"  {len(items)} events returned (Total in DB: {data.get('total', len(items)) if isinstance(data, dict) else len(items)})")
    if items:
        print(f"  Latest: {items[0].get('event_type')} | {items[0].get('action')}")

    # 9. Audit: employee should lack permission
    print("\n--- Audit Access (employee, should fail) ---")
    r = httpx.get(f"{BASE}/api/v1/audit/events",
        headers={"Authorization": f"Bearer {tokens['employee']}"})
    print(f"  Status={r.status_code} (expected 403 or error)")

    # 10. User Management (admin)
    print("\n--- User Management API ---")
    r = httpx.get(f"{BASE}/api/v1/users", headers={"Authorization": f"Bearer {tokens['admin']}"})
    u_page = r.json()
    print(f"  List users: status={r.status_code} total={u_page.get('total')}")

    # 11. Chain verify
    print("\n--- Chain Integrity ---")
    r = httpx.get(f"{BASE}/api/v1/audit/verify",
        headers={"Authorization": f"Bearer {tokens['admin']}"})
    print(f"  {r.json()}")

    print("\n" + "=" * 60)
    print("  SMOKE TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
