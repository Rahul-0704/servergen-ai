"""
End-to-end smoke test for ServerGen AI -- Modules 1 & 2.

Tests every API endpoint against a running server (http://127.0.0.1:8000).
Run AFTER: seed_db.py + uvicorn src.app:app

Usage:
    python scripts/e2e_test.py
"""
import sys
import os
import httpx

BASE = "http://127.0.0.1:8000"
PASS = 0
FAIL = 0

def ok(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}  -- {detail}")

def section(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")

# -- Health --------------------------------------------------------
section("1. Health Check")
r = httpx.get(f"{BASE}/health")
ok("GET /health -> 200", r.status_code == 200, f"got {r.status_code}")
ok("status=healthy", r.json().get("status") == "healthy")

r2 = httpx.get(f"{BASE}/api/v1/health")
ok("GET /api/v1/health -> 200", r2.status_code == 200, f"got {r2.status_code}")
ok("database field present", "database" in r2.json())

# -- Auth: Login ---------------------------------------------------
section("2. Authentication -- Login")

users = [
    ("admin",    "admin",      "administrator"),
    ("operator", "Operator1!", "it_operator"),
    ("analyst",  "Analyst1!",  "security_analyst"),
    ("manager",  "Manager1!",  "manager"),
    ("employee", "Employee1!", "general_employee"),
]
tokens = {}
for uname, pwd, role in users:
    r = httpx.post(f"{BASE}/api/v1/auth/login", json={"username": uname, "password": pwd})
    ok(f"Login {uname} -> 200", r.status_code == 200, f"got {r.status_code}: {r.text[:120]}")
    if r.status_code == 200:
        d = r.json()
        tokens[uname] = {"access": d["access_token"], "refresh": d["refresh_token"]}
        ok(f"  token_type=bearer", d.get("token_type") == "bearer")
        ok(f"  expires_in={d.get('expires_in')}", d.get("expires_in", 0) > 0)

# Bad login
r = httpx.post(f"{BASE}/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
ok("Bad password -> 401", r.status_code == 401, f"got {r.status_code}")

r = httpx.post(f"{BASE}/api/v1/auth/login", json={"username": "nouser", "password": "x"})
ok("Unknown user -> 401", r.status_code == 401, f"got {r.status_code}")

# -- Auth: /me -----------------------------------------------------
section("3. Authentication -- Profile")
for uname in ["admin", "operator", "employee"]:
    t = tokens.get(uname, {}).get("access")
    if not t:
        continue
    r = httpx.get(f"{BASE}/api/v1/auth/me", headers={"Authorization": f"Bearer {t}"})
    ok(f"GET /me as {uname} -> 200", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        ok(f"  username={uname}", r.json().get("username") == uname)

# No token
r = httpx.get(f"{BASE}/api/v1/auth/me")
ok("GET /me without token -> 401/403", r.status_code in (401, 403), f"got {r.status_code}")

# -- Auth: Refresh -------------------------------------------------
section("4. Authentication -- Token Refresh")
admin_refresh = tokens.get("admin", {}).get("refresh")
if admin_refresh:
    r = httpx.post(f"{BASE}/api/v1/auth/refresh", json={"refresh_token": admin_refresh})
    ok("Refresh admin token -> 200", r.status_code == 200, f"got {r.status_code}: {r.text[:120]}")
    if r.status_code == 200:
        d = r.json()
        tokens["admin"]["access"] = d["access_token"]
        tokens["admin"]["refresh"] = d["refresh_token"]
        ok("  new access token differs", d["access_token"] != admin_refresh)

    # Reuse old refresh token -> should fail (reuse detection)
    r2 = httpx.post(f"{BASE}/api/v1/auth/refresh", json={"refresh_token": admin_refresh})
    ok("Reuse old refresh -> fail", r2.status_code >= 400, f"got {r2.status_code}")

# -- Auth: Logout --------------------------------------------------
section("5. Authentication -- Logout")
emp_refresh = tokens.get("employee", {}).get("refresh")
if emp_refresh:
    r = httpx.post(f"{BASE}/api/v1/auth/logout", json={"refresh_token": emp_refresh})
    ok("Logout employee -> 204", r.status_code == 204, f"got {r.status_code}")

# -- RBAC: Protected endpoints -------------------------------------
section("6. RBAC -- Permission Enforcement")

admin_token = tokens.get("admin", {}).get("access")
if admin_token:
    r = httpx.get(f"{BASE}/api/v1/audit/events?limit=5", headers={"Authorization": f"Bearer {admin_token}"})
    ok("Admin -> audit/events -> 200", r.status_code == 200, f"got {r.status_code}")

emp_token = tokens.get("employee", {}).get("access")
if emp_token:
    r = httpx.get(f"{BASE}/api/v1/audit/events?limit=5", headers={"Authorization": f"Bearer {emp_token}"})
    ok("Employee -> audit/events -> 403", r.status_code == 403, f"got {r.status_code}")

# -- AI Orchestrator ------------------------------------------------
section("7. AI Orchestrator")
if admin_token:
    r = httpx.post(
        f"{BASE}/api/v1/ai/execute",
        json={"input": "What is 2+2?", "data_sensitivity": "public"},
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=30,
    )
    ok("AI execute -> 200", r.status_code == 200, f"got {r.status_code}: {r.text[:200]}")
    if r.status_code == 200:
        d = r.json()
        ok("  has task_category", "task_category" in d)
        ok("  has risk_level", "risk_level" in d)
        ok("  has policy_decision", "policy_decision" in d)

    # Calculator tool
    r = httpx.post(
        f"{BASE}/api/v1/ai/execute",
        json={"input": "calc", "tool": "calculator", "tool_parameters": {"expression": "2+2*10"}, "data_sensitivity": "public"},
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    ok("Calculator tool -> 200", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        ok("  tool_output=22", str(d.get("tool_output", "")) == "22", f"got {d.get('tool_output')}")

    # Blocked tool
    r = httpx.post(
        f"{BASE}/api/v1/ai/execute",
        json={"input": "hack", "tool": "shell_execute", "data_sensitivity": "public"},
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    ok("Blocked tool -> 200 (denied)", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        ok("  policy=deny", r.json().get("policy_decision") == "deny")

    # Models list
    r = httpx.get(f"{BASE}/api/v1/ai/models", headers={"Authorization": f"Bearer {admin_token}"})
    ok("GET /ai/models -> 200", r.status_code == 200, f"got {r.status_code}")

    # Tasks list
    r = httpx.get(f"{BASE}/api/v1/ai/tasks", headers={"Authorization": f"Bearer {admin_token}"})
    ok("GET /ai/tasks -> 200", r.status_code == 200, f"got {r.status_code}")

# Employee with ai.execute
if emp_token:
    r = httpx.post(f"{BASE}/api/v1/auth/login", json={"username": "employee", "password": "Employee1!"})
    if r.status_code == 200:
        emp_token = r.json()["access_token"]
    r = httpx.post(
        f"{BASE}/api/v1/ai/execute",
        json={"input": "hello", "data_sensitivity": "public"},
        headers={"Authorization": f"Bearer {emp_token}"},
        timeout=30,
    )
    ok("Employee -> AI execute -> 200", r.status_code == 200, f"got {r.status_code}")

# -- Audit Ledger ---------------------------------------------------
section("8. Audit Ledger")
if admin_token:
    r = httpx.get(f"{BASE}/api/v1/audit/events?limit=20", headers={"Authorization": f"Bearer {admin_token}"})
    ok("Audit events -> 200", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        body = r.json()
        # Response may be {"items": [...]} or a plain list
        events = body.get("items", body) if isinstance(body, dict) else body
        if not isinstance(events, list):
            events = []
        ok(f"  has events ({len(events)})", len(events) > 0)
        types = [e.get("event_type") for e in events if isinstance(e, dict)]
        ok("  has login events", any("login" in str(t).lower() for t in types), f"got types: {set(types)}")

    r = httpx.get(f"{BASE}/api/v1/audit/verify", headers={"Authorization": f"Bearer {admin_token}"})
    ok("Chain verify -> 200", r.status_code == 200, f"got {r.status_code}")

# -- Users API ------------------------------------------------------
section("9. User Management")
if admin_token:
    r = httpx.get(f"{BASE}/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"})
    ok("GET /users (admin) -> 200", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        users_list = data.get("items", data) if isinstance(data, dict) else data
        ok(f"  has users ({len(users_list)})", len(users_list) >= 5)

# -- Test Interface -------------------------------------------------
section("10. Test Interface")
r = httpx.get(f"{BASE}/test")
ok("GET /test (HTML dashboard) -> 200", r.status_code == 200, f"got {r.status_code}")
ok("  returns HTML", "text/html" in r.headers.get("content-type", ""), f"got {r.headers.get('content-type')}")

# -- Summary --------------------------------------------------------
section("SUMMARY")
total = PASS + FAIL
print(f"  Passed: {PASS}/{total}")
print(f"  Failed: {FAIL}/{total}")
if FAIL == 0:
    print("\n  ALL TESTS PASSED -- Modules 1 & 2 are fully working!")
else:
    print(f"\n  WARNING: {FAIL} test(s) failed -- see details above.")
sys.exit(0 if FAIL == 0 else 1)
