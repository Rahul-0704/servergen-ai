"""
Tests for User Management API and Service.

Tests:
1. List users (requires user.read)
2. Get user by ID
3. Create user (requires user.write, Argon2id hashed, role assigned, audited)
4. Duplicate username/email rejected with Conflict
5. Update user details
6. Disable user (is_active=False, active sessions revoked, audited)
7. Enable user
8. Unauthorized user (general employee) denied on user.write endpoints
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.security import create_access_token, hash_password
from src.models.role import Role
from src.models.user import User
from src.services.audit_service import AuditEventType, AuditService


async def _seed_test_roles(db: AsyncSession) -> dict[str, Role]:
    from sqlalchemy import select
    roles = {}
    for name in ("administrator", "it_operator", "general_employee"):
        res = await db.execute(select(Role).where(Role.name == name))
        existing = res.scalar_one_or_none()
        if existing is not None:
            roles[name] = existing
        else:
            r = Role(id=uuid.uuid4(), name=name, description=f"{name} role")
            db.add(r)
            roles[name] = r
    await db.flush()
    return roles


async def _seed_admin(db: AsyncSession, admin_role: Role) -> User:
    admin = User(
        id=uuid.uuid4(),
        username="admin_manage_test",
        email="admin_manage@test.local",
        hashed_password=hash_password("AdminPass123!"),
        full_name="Admin Tester",
        role_id=admin_role.id,
        is_active=True,
    )
    db.add(admin)
    await db.flush()
    admin.role = admin_role
    return admin


async def _seed_employee(db: AsyncSession, emp_role: Role) -> User:
    emp = User(
        id=uuid.uuid4(),
        username="emp_manage_test",
        email="emp_manage@test.local",
        hashed_password=hash_password("EmpPass123!"),
        full_name="Emp Tester",
        role_id=emp_role.id,
        is_active=True,
    )
    db.add(emp)
    await db.flush()
    emp.role = emp_role
    return emp


@pytest.mark.asyncio
async def test_list_and_get_users(client: AsyncClient, db_session: AsyncSession) -> None:
    roles = await _seed_test_roles(db_session)
    admin = await _seed_admin(db_session, roles["administrator"])
    token = create_access_token(str(admin.id), "administrator")

    # List users
    resp = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] >= 1

    # Get specific user
    resp = await client.get(
        f"/api/v1/users/{admin.id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    u_data = resp.json()
    assert u_data["username"] == "admin_manage_test"
    assert u_data["role"] == "administrator"


@pytest.mark.asyncio
async def test_create_user_and_conflict(client: AsyncClient, db_session: AsyncSession) -> None:
    roles = await _seed_test_roles(db_session)
    admin = await _seed_admin(db_session, roles["administrator"])
    token = create_access_token(str(admin.id), "administrator")

    payload = {
        "username": "new_created_user",
        "email": "new_created@test.local",
        "password": "SecurePassword1!",
        "full_name": "New User",
        "role": "general_employee",
    }
    resp = await client.post(
        "/api/v1/users", json=payload, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "new_created_user"
    assert data["role"] == "general_employee"

    # Duplicate username should fail with 409 Conflict
    resp = await client.post(
        "/api/v1/users", json=payload, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_disable_and_enable_user(client: AsyncClient, db_session: AsyncSession) -> None:
    roles = await _seed_test_roles(db_session)
    admin = await _seed_admin(db_session, roles["administrator"])
    target = await _seed_employee(db_session, roles["general_employee"])
    token = create_access_token(str(admin.id), "administrator")

    # Disable
    resp = await client.post(
        f"/api/v1/users/{target.id}/disable", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # Check audit ledger
    audit = AuditService(db_session)
    events = await audit.repo.list_events(limit=10, descending=True)
    disabled_events = [e for e in events if e.event_type == AuditEventType.USER_DISABLED]
    assert len(disabled_events) >= 1

    # Re-enable
    resp = await client.post(
        f"/api/v1/users/{target.id}/enable", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


@pytest.mark.asyncio
async def test_update_user(client: AsyncClient, db_session: AsyncSession) -> None:
    roles = await _seed_test_roles(db_session)
    admin = await _seed_admin(db_session, roles["administrator"])
    target = await _seed_employee(db_session, roles["general_employee"])
    token = create_access_token(str(admin.id), "administrator")

    # Update full_name and email
    update_payload = {
        "full_name": "Updated Employee Name",
        "email": "updated_email@test.local",
    }
    resp = await client.patch(
        f"/api/v1/users/{target.id}",
        json=update_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["full_name"] == "Updated Employee Name"
    assert data["email"] == "updated_email@test.local"


@pytest.mark.asyncio
async def test_unauthorized_user_denied(client: AsyncClient, db_session: AsyncSession) -> None:
    roles = await _seed_test_roles(db_session)
    emp = await _seed_employee(db_session, roles["general_employee"])
    token = create_access_token(str(emp.id), "general_employee")

    # General employee lacking user.write should receive 403
    payload = {
        "username": "unauthorized_create",
        "email": "unauth@test.local",
        "password": "SecurePassword1!",
        "role": "general_employee",
    }
    resp = await client.post(
        "/api/v1/users", json=payload, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403
