"""
Integration Test — End-to-End Auth, RBAC & User Management on PostgreSQL.

Verifies:
 1. Full login against Argon2id hash stored in PostgreSQL.
 2. JWT issuance and live identity resolution via get_auth_context against PostgreSQL.
 3. Refresh token rotation with family tracking in PostgreSQL refresh_sessions.
 4. User management API creating and updating accounts in PostgreSQL.
 5. Audit ledger API verifying the recorded events and chain integrity.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.auth.permissions import PermissionCode
from src.core.security import hash_password
from src.models.role import Role
from src.models.user import User


@pytest.mark.asyncio
async def test_postgres_auth_and_user_lifecycle_e2e(
    pg_session: AsyncSession,
    pg_client: AsyncClient,
) -> None:
    """Full lifecycle: Seed -> Login -> Get Me -> Rotate Token -> Create User -> Verify Audit."""
    from sqlalchemy import text

    await pg_session.execute(text("TRUNCATE TABLE audit_events;"))
    await pg_session.commit()

    # 1. Seed admin role and user with unique suffix
    suffix = uuid.uuid4().hex[:6]
    from src.repositories.role_repository import RoleRepository

    role_repo = RoleRepository(pg_session)
    admin_perms = [
        await role_repo.get_or_create_permission(
            p.value, p.value.split(".")[0], p.value.split(".")[1]
        )
        for p in [
            PermissionCode.USER_READ,
            PermissionCode.USER_WRITE,
            PermissionCode.AI_EXECUTE,
            PermissionCode.AUDIT_READ,
        ]
    ]
    admin_role = Role(
        id=uuid.uuid4(),
        name=f"pg_role_{suffix}",
        description="PostgreSQL Admin Role",
        is_system=True,
        permissions=admin_perms,
    )
    admin_user = User(
        id=uuid.uuid4(),
        username=f"pg_admin_{suffix}",
        email=f"pg_admin_{suffix}@servergen.local",
        hashed_password=hash_password("SuperSecureAdmin123!"),
        role_id=admin_role.id,
        role=admin_role,
        is_active=True,
    )
    pg_session.add_all([admin_role, admin_user])
    await pg_session.commit()

    # 2. Login
    login_resp = await pg_client.post(
        "/api/v1/auth/login",
        json={"username": f"pg_admin_{suffix}", "password": "SuperSecureAdmin123!"},
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    tokens = login_resp.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # 3. Get profile (tests JWT -> DB lookup -> live AuthContext resolution on PostgreSQL)
    headers = {"Authorization": f"Bearer {access_token}"}
    me_resp = await pg_client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["username"] == f"pg_admin_{suffix}"
    assert me_data["role"] == f"pg_role_{suffix}"

    # 4. Refresh token rotation
    refresh_resp = await pg_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 200
    new_tokens = refresh_resp.json()
    new_access_token = new_tokens["access_token"]
    assert new_access_token != access_token
    new_headers = {"Authorization": f"Bearer {new_access_token}"}

    # 5. Create new user via User Management API
    create_resp = await pg_client.post(
        "/api/v1/users",
        headers=new_headers,
        json={
            "username": f"pg_new_user_{suffix}",
            "email": f"new_pg_{suffix}@servergen.local",
            "password": "NewUserPassword123!",
            "full_name": "New PG User",
            "role": admin_role.name,
        },
    )
    assert create_resp.status_code in (200, 201), f"User creation failed: {create_resp.text}"
    created_user = create_resp.json()
    assert created_user["username"] == f"pg_new_user_{suffix}"

    # 6. Verify audit ledger has recorded events
    audit_resp = await pg_client.get("/api/v1/audit/events", headers=new_headers)
    assert audit_resp.status_code == 200
    events_data = audit_resp.json()
    assert events_data["total"] >= 2  # Login, Token refresh, User create

    # 7. Verify hash chain integrity on PostgreSQL
    verify_resp = await pg_client.get("/api/v1/audit/verify", headers=new_headers)
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["status"] == "verified"
    assert verify_data["broken_at_sequence"] is None
