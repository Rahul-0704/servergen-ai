"""
ServerGen AI — Centralized RBAC Guard.

One authorization mechanism used by ALL protected endpoints.
No scattered role checks — everything passes through AuthorizationService.

Flow:
    Bearer JWT → live User row (active? current role?) → role permissions
               → AuthorizationService → ALLOW / DENY (+ audit on DENY)

The role inside the JWT is NOT trusted for authorization: the user is re-read
from the database on every request, so disabling a user or changing a role takes
effect immediately instead of when the access token expires.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.permissions import DEFAULT_ROLE_PERMISSIONS, PermissionCode, SystemRole
from src.core.database import get_db
from src.core.exceptions import AuthenticationError, AuthorizationError
from src.core.security import decode_token

logger = logging.getLogger("servergen.rbac")

_bearer_scheme = HTTPBearer(auto_error=False)


# ── AuthContext: the resolved identity for the current request ──────────


class AuthContext:
    """Resolved user identity and permissions for the current request."""

    __slots__ = ("permissions", "role", "user_id", "username")

    def __init__(self, user_id: str, role: str, permissions: set[str], username: str = "") -> None:
        self.user_id = user_id
        self.role = role
        self.permissions = permissions
        self.username = username

    def has_permission(self, permission: str | PermissionCode) -> bool:
        """Check if the current user has a specific permission."""
        return str(permission) in self.permissions

    def has_any_permission(self, *permissions: str | PermissionCode) -> bool:
        """Check if the current user has at least one of the given permissions."""
        return any(str(p) in self.permissions for p in permissions)

    def has_all_permissions(self, *permissions: str | PermissionCode) -> bool:
        """Check if the current user has all of the given permissions."""
        return all(str(p) in self.permissions for p in permissions)

    def __repr__(self) -> str:
        return f"<AuthContext(user_id={self.user_id!r}, role={self.role!r})>"


def resolve_permissions(role_name: str) -> set[str]:
    """Permission codenames for a role from the centralized policy mapping (unknown → none)."""
    try:
        system_role = SystemRole(role_name)
    except ValueError:
        logger.warning("Unknown role %r — granting no permissions", role_name)
        return set()
    return {str(p) for p in DEFAULT_ROLE_PERMISSIONS.get(system_role, set())}


# Backwards-compatible private alias
_resolve_permissions = resolve_permissions


# ── Dependency: resolve JWT → AuthContext ────────────────────────────────


async def get_auth_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthContext:
    """
    Resolve the Bearer token into an AuthContext.

    1. Decode & validate the JWT (fixed algorithm, type=access, iss/aud/exp/sub).
    2. Load the live user; reject missing/disabled users.
    3. Use the user's CURRENT role to resolve permissions.
    """
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Authentication required")

    try:
        payload = decode_token(credentials.credentials, expected_type="access")
        user_uuid = uuid.UUID(payload["sub"])
    except Exception as exc:
        raise AuthenticationError("Invalid or expired access token") from exc

    from src.repositories.user_repository import UserRepository

    user = await UserRepository(db).get_by_id(user_uuid)
    if user is None or not user.is_active or user.role is None:
        raise AuthenticationError("Account is not available")

    role_name = user.role.name
    # Union canonical code definitions with any dynamic DB-assigned permissions
    permissions = resolve_permissions(role_name)
    role_perms = getattr(user.role, "permissions", None)
    if role_perms:
        permissions = permissions | {str(p.codename) for p in role_perms}

    return AuthContext(
        user_id=str(user.id),
        role=role_name,
        permissions=permissions,
        username=user.username,
    )


# ── Authorization Service ───────────────────────────────────────────────


class AuthorizationService:
    """Centralized authorization — the ONLY place where permission checks happen."""

    def __init__(self, context: AuthContext) -> None:
        self.context = context

    def require_permission(self, permission: str | PermissionCode) -> None:
        """Raise AuthorizationError if the user does not have the required permission."""
        if not self.context.has_permission(permission):
            logger.warning(
                "Authorization denied: user=%s role=%s missing=%s",
                self.context.user_id,
                self.context.role,
                permission,
            )
            raise AuthorizationError(f"Permission '{permission}' required")

    def require_any_permission(self, *permissions: str | PermissionCode) -> None:
        """Raise AuthorizationError if the user lacks ALL the given permissions."""
        if not self.context.has_any_permission(*permissions):
            raise AuthorizationError(f"One of {[str(p) for p in permissions]} required")

    def require_all_permissions(self, *permissions: str | PermissionCode) -> None:
        """Raise AuthorizationError if the user lacks ANY of the given permissions."""
        if not self.context.has_all_permissions(*permissions):
            missing = [str(p) for p in permissions if not self.context.has_permission(p)]
            raise AuthorizationError(f"Missing permissions: {missing}")


# ── Convenience dependency factories ────────────────────────────────────


def require_permission(permission: str | PermissionCode):
    """
    Dependency factory: require a single permission, auditing denials.

    Usage::

        @router.get("/x", dependencies=[Depends(require_permission(PermissionCode.AUDIT_READ))])
    """

    async def _check(
        request: Request,
        auth: Annotated[AuthContext, Depends(get_auth_context)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> AuthContext:
        try:
            AuthorizationService(auth).require_permission(permission)
        except AuthorizationError:
            from src.services.audit_service import AuditEventType, AuditService

            await AuditService(db).record(
                event_type=AuditEventType.AUTHORIZATION_DENIED,
                action="authorization_denied",
                request_id=getattr(request.state, "request_id", "unknown"),
                decision="deny",
                user_id=auth.user_id,
                role=auth.role,
                resource=request.url.path,
                metadata={"required_permission": str(permission), "method": request.method},
            )
            # The request transaction rolls back on the raised error — persist the audit first.
            await db.commit()
            raise
        return auth

    return _check
