"""
Phase C Tests — RBAC & Permissions.

Tests:
 1. Permission codenames are well-formed (resource.action)
 2. All system roles have permission mappings
 3. ADMIN has all permissions
 4. GENERAL_EMPLOYEE has restricted permissions
 5. AuthContext correctly checks single and multiple permissions
 6. AuthorizationService denies unauthorized access
 7. AuthorizationService allows authorized access
 8. Unknown role gets no permissions
 9. require_permission dependency factory works
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from src.auth.permissions import (
    DEFAULT_ROLE_PERMISSIONS,
    PermissionCode,
    SystemRole,
    get_permission_resource_action,
)
from src.auth.rbac import (
    AuthContext,
    AuthorizationService,
    _resolve_permissions,
    get_auth_context,
)
from src.core.exceptions import AuthorizationError
from src.core.security import create_access_token
from src.models.role import Permission, Role
from src.models.user import User

# ── Test 1: Permission codenames are well-formed ────────────────────────


def test_permission_codenames_format() -> None:
    """All permission codenames follow 'resource.action' format."""
    for perm in PermissionCode:
        resource, action = get_permission_resource_action(perm.value)
        assert resource, f"Empty resource in {perm.value}"
        assert action, f"Empty action in {perm.value}"
        assert "." not in resource, f"Nested dots in resource: {perm.value}"


# ── Test 2: All system roles have mappings ──────────────────────────────


def test_all_system_roles_have_mappings() -> None:
    """Every SystemRole has a corresponding entry in DEFAULT_ROLE_PERMISSIONS."""
    for role in SystemRole:
        assert role in DEFAULT_ROLE_PERMISSIONS, f"Missing mapping for {role}"
        assert isinstance(DEFAULT_ROLE_PERMISSIONS[role], set)


# ── Test 3: ADMIN has all permissions ───────────────────────────────────


def test_admin_has_all_permissions() -> None:
    """ADMIN role should have every defined permission."""
    admin_perms = DEFAULT_ROLE_PERMISSIONS[SystemRole.ADMIN]
    for perm in PermissionCode:
        assert perm in admin_perms, f"ADMIN missing {perm.value}"


# ── Test 4: GENERAL_EMPLOYEE is restricted ──────────────────────────────


def test_general_employee_is_restricted() -> None:
    """GENERAL_EMPLOYEE should NOT have admin, security, or approval permissions."""
    emp_perms = DEFAULT_ROLE_PERMISSIONS[SystemRole.GENERAL_EMPLOYEE]
    assert PermissionCode.ADMIN_MANAGE not in emp_perms
    assert PermissionCode.SECURITY_EXECUTE not in emp_perms
    assert PermissionCode.APPROVAL_APPROVE not in emp_perms
    assert PermissionCode.SYSTEM_EXECUTE not in emp_perms
    # But should have basic access
    assert PermissionCode.DOCUMENT_READ in emp_perms
    assert PermissionCode.AI_EXECUTE in emp_perms


# ── Test 5: AuthContext permission checks ───────────────────────────────


def test_auth_context_single_permission() -> None:
    """AuthContext.has_permission works for single permission checks."""
    ctx = AuthContext(
        user_id="user-1",
        role="manager",
        permissions={"document.read", "document.write", "approval.approve"},
    )
    assert ctx.has_permission("document.read") is True
    assert ctx.has_permission(PermissionCode.DOCUMENT_READ) is True
    assert ctx.has_permission("admin.manage") is False


def test_auth_context_multiple_permissions() -> None:
    """AuthContext.has_any_permission and has_all_permissions work correctly."""
    ctx = AuthContext(
        user_id="user-1",
        role="manager",
        permissions={"document.read", "system.read"},
    )
    # has_any_permission
    assert ctx.has_any_permission("document.read", "admin.manage") is True
    assert ctx.has_any_permission("admin.manage", "security.execute") is False

    # has_all_permissions
    assert ctx.has_all_permissions("document.read", "system.read") is True
    assert ctx.has_all_permissions("document.read", "admin.manage") is False


# ── Test 6: AuthorizationService denies unauthorized ────────────────────


def test_authorization_denies_missing_permission() -> None:
    """AuthorizationService raises AuthorizationError for missing permissions."""
    ctx = AuthContext(
        user_id="user-1",
        role="general_employee",
        permissions={"document.read", "ai.execute"},
    )
    svc = AuthorizationService(ctx)

    with pytest.raises(AuthorizationError):
        svc.require_permission(PermissionCode.ADMIN_MANAGE)

    with pytest.raises(AuthorizationError):
        svc.require_any_permission("admin.manage", "security.execute")

    with pytest.raises(AuthorizationError):
        svc.require_all_permissions("document.read", "admin.manage")


# ── Test 7: AuthorizationService allows authorized ──────────────────────


def test_authorization_allows_valid_permission() -> None:
    """AuthorizationService does NOT raise for valid permissions."""
    ctx = AuthContext(
        user_id="admin-1",
        role="administrator",
        permissions={str(p) for p in PermissionCode},
    )
    svc = AuthorizationService(ctx)

    # Should not raise for any permission
    svc.require_permission(PermissionCode.ADMIN_MANAGE)
    svc.require_permission(PermissionCode.SECURITY_EXECUTE)
    svc.require_any_permission("document.read", "admin.manage")
    svc.require_all_permissions("document.read", "admin.manage", "security.read")


# ── Test 8: Unknown role gets no permissions ────────────────────────────


def test_unknown_role_no_permissions() -> None:
    """An unrecognized role name resolves to an empty permission set."""
    perms = _resolve_permissions("nonexistent_role")
    assert perms == set()


# ── Test 9: _resolve_permissions for known roles ────────────────────────


def test_resolve_permissions_for_known_roles() -> None:
    """All known roles resolve to the expected permission sets."""
    admin_perms = _resolve_permissions(SystemRole.ADMIN.value)
    assert len(admin_perms) == len(PermissionCode)

    emp_perms = _resolve_permissions(SystemRole.GENERAL_EMPLOYEE.value)
    assert "document.read" in emp_perms
    assert "admin.manage" not in emp_perms


# ── Test 10: Dynamic DB Permissions ─────────────────────────────────────


@pytest.mark.asyncio
async def test_get_auth_context_dynamic_db_permissions(
    db_session: AsyncSession,
) -> None:
    """get_auth_context uses dynamic permissions from role.permissions when present in DB."""
    perm = Permission(
        id=uuid.uuid4(),
        codename="custom.execute",
        description="Custom execution",
        resource="custom",
        action="execute",
    )
    role = Role(
        id=uuid.uuid4(),
        name="custom_role",
        description="Custom Role",
        is_system=False,
        permissions=[perm],
    )
    user = User(
        id=uuid.uuid4(),
        username="dynamic_user",
        email="dynamic@servergen.local",
        hashed_password="argon2id$mocked",
        role_id=role.id,
        role=role,
        is_active=True,
    )
    db_session.add_all([perm, role, user])
    await db_session.flush()

    token = create_access_token(user_id=user.id, role="custom_role")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    ctx = await get_auth_context(creds, db_session)
    assert ctx.user_id == str(user.id)
    assert ctx.role == "custom_role"
    assert "custom.execute" in ctx.permissions
