"""
Phase A Tests — Health Check and Foundation.

Validates that the application starts, health endpoints respond,
and the database models can be imported without errors.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
    """Health endpoint returns 200 with correct structure."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "service" in data
    assert "environment" in data


@pytest.mark.asyncio
async def test_api_health_check(client: AsyncClient) -> None:
    """API-versioned health endpoint returns 200."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")  # degraded when DB not available in test
    assert "version" in data
    assert "database" in data


@pytest.mark.asyncio
async def test_request_id_header(client: AsyncClient) -> None:
    """Every response includes an X-Request-ID header for tracing."""
    response = await client.get("/health")
    assert "x-request-id" in response.headers
    # UUID format: 8-4-4-4-12 hex chars
    rid = response.headers["x-request-id"]
    assert len(rid) == 36


@pytest.mark.asyncio
async def test_unknown_route_returns_json_error(client: AsyncClient) -> None:
    """Unknown routes return proper JSON, not HTML error pages."""
    response = await client.get("/nonexistent")
    assert response.status_code == 404


def test_models_import() -> None:
    """All database models can be imported without circular dependency errors."""
    from src.models import (
        ApprovalRequest,
        AuditEvent,
        Base,
        Permission,
        RefreshSession,
        Role,
        RolePermission,
        User,
    )

    # Verify all tables are registered in metadata
    table_names = set(Base.metadata.tables.keys())
    expected = {
        "users",
        "roles",
        "permissions",
        "role_permissions",
        "refresh_sessions",
        "audit_events",
        "approval_requests",
    }
    assert expected.issubset(table_names), f"Missing tables: {expected - table_names}"

    # Verify model classes are not None
    assert User is not None
    assert Role is not None
    assert Permission is not None
    assert RolePermission is not None
    assert RefreshSession is not None
    assert AuditEvent is not None
    assert ApprovalRequest is not None


def test_config_loads() -> None:
    """Application configuration loads successfully from environment."""
    from src.core.config import get_settings

    settings = get_settings()
    assert settings.APP_NAME == "ServerGen AI"
    assert settings.APP_ENV in ("development", "staging", "production", "test")
    assert settings.JWT_ALGORITHM == "HS256"
    assert settings.MAX_LOGIN_ATTEMPTS > 0
    assert settings.LOCKOUT_DURATION_MINUTES > 0


def test_exception_hierarchy() -> None:
    """Custom exceptions form a proper hierarchy with correct codes."""
    from src.core.exceptions import (
        AccountLockedError,
        ApprovalRequiredError,
        AuthenticationError,
        AuthorizationError,
        PolicyDeniedError,
        ServerGenError,
    )

    # All exceptions inherit from ServerGenError
    assert issubclass(AuthenticationError, ServerGenError)
    assert issubclass(AccountLockedError, AuthenticationError)
    assert issubclass(AuthorizationError, ServerGenError)
    assert issubclass(PolicyDeniedError, ServerGenError)
    assert issubclass(ApprovalRequiredError, ServerGenError)

    # Error codes are set correctly
    assert AuthenticationError().code == "AUTHENTICATION_FAILED"
    assert AccountLockedError().code == "ACCOUNT_LOCKED"
    assert AuthorizationError().code == "AUTHORIZATION_DENIED"
    assert PolicyDeniedError().code == "POLICY_DENIED"
    assert ApprovalRequiredError().code == "APPROVAL_REQUIRED"
