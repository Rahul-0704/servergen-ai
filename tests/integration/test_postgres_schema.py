"""
Integration Test — PostgreSQL Schema & Type Compatibility.

Verifies:
 1. Live connectivity to PostgreSQL 16.
 2. Existence of all 7 core tables in PostgreSQL.
 3. Native postgresql.UUID and postgresql.JSON storage and retrieval.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.approval import ApprovalRequest
from src.models.role import Role
from src.models.user import User


@pytest.mark.asyncio
async def test_postgres_connection_and_version(pg_session: AsyncSession) -> None:
    """PostgreSQL is connected and returns valid version."""
    res = await pg_session.execute(text("SELECT version();"))
    version_str = res.scalar_one()
    assert "PostgreSQL" in version_str


@pytest.mark.asyncio
async def test_postgres_tables_exist(pg_session: AsyncSession) -> None:
    """All core application tables exist in the PostgreSQL database."""
    res = await pg_session.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public';
            """
        )
    )
    tables = {row[0] for row in res.fetchall()}
    expected_tables = {
        "roles",
        "permissions",
        "role_permissions",
        "users",
        "refresh_sessions",
        "approval_requests",
        "audit_events",
    }
    missing = expected_tables - tables
    assert not missing, f"Missing tables in PostgreSQL: {missing}"


@pytest.mark.asyncio
async def test_postgres_uuid_and_json_handling(pg_session: AsyncSession) -> None:
    """PostgreSQL natively persists and reads back UUID and JSON columns."""
    role_id = uuid.uuid4()
    role = Role(
        id=role_id,
        name=f"test_role_{role_id.hex[:6]}",
        description="Integration test role",
        is_system=False,
    )
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        username=f"pg_user_{user_id.hex[:6]}",
        email=f"pg_{user_id.hex[:6]}@servergen.local",
        hashed_password="argon2id$mocked",
        role_id=role_id,
        role=role,
        is_active=True,
    )
    approval_id = uuid.uuid4()
    req = ApprovalRequest(
        id=approval_id,
        request_id=f"req_{approval_id.hex[:6]}",
        requester_user_id=user_id,
        requester_role="integration_tester",
        operation_summary="Test operation",
        operation_fingerprint="abc123hash",
        operation_payload={"key": "value", "count": 42, "nested": {"enabled": True}},
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )

    pg_session.add_all([role, user])
    await pg_session.flush()

    pg_session.add(req)
    await pg_session.flush()

    # Re-query directly to verify JSON and UUID types
    loaded_req = await pg_session.get(ApprovalRequest, approval_id)
    assert loaded_req is not None
    assert loaded_req.id == approval_id
    assert loaded_req.operation_payload["count"] == 42
    assert loaded_req.operation_payload["nested"]["enabled"] is True
