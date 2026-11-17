"""
ServerGen AI — Permission Codenames & Role→Permission Mappings.

Centralized definition of all system permissions and the default role
assignments. Permissions use a 'resource.action' naming convention.

Roles: ADMIN, IT_OPERATOR, SECURITY_ANALYST, MANAGER, GENERAL_EMPLOYEE
"""

from __future__ import annotations

from enum import StrEnum

# ── System Roles ────────────────────────────────────────────────────────


class SystemRole(StrEnum):
    """System-defined role names."""

    ADMIN = "administrator"
    IT_OPERATOR = "it_operator"
    SECURITY_ANALYST = "security_analyst"
    MANAGER = "manager"
    GENERAL_EMPLOYEE = "general_employee"


# ── Permission Codenames ────────────────────────────────────────────────


class PermissionCode(StrEnum):
    """
    All system permission codenames.

    Format: resource.action
    Permissions are assigned to roles, never directly to users.
    """

    # Document management
    DOCUMENT_READ = "document.read"
    DOCUMENT_WRITE = "document.write"
    DOCUMENT_UPLOAD = "document.upload"
    DOCUMENT_UPDATE = "document.update"
    DOCUMENT_DELETE = "document.delete"
    DOCUMENT_REINDEX = "document.reindex"
    DOCUMENT_MANAGE_PERMISSIONS = "document.manage_permissions"
    RAG_EVAL = "rag.eval"

    # System operations
    SYSTEM_READ = "system.read"
    SYSTEM_EXECUTE = "system.execute"

    # Security
    SECURITY_READ = "security.read"
    SECURITY_EXECUTE = "security.execute"

    # Reporting
    REPORT_GENERATE = "report.generate"

    # Approvals
    APPROVAL_APPROVE = "approval.approve"

    # Administration
    ADMIN_MANAGE = "admin.manage"

    # User management
    USER_READ = "user.read"
    USER_WRITE = "user.write"

    # AI tasks
    AI_EXECUTE = "ai.execute"
    AI_READ = "ai.read"

    # Audit
    AUDIT_READ = "audit.read"


# ── Default Role → Permission Mappings ──────────────────────────────────

# Each role gets a set of permission codenames.
# ADMIN gets everything; other roles are progressively restricted.

DEFAULT_ROLE_PERMISSIONS: dict[SystemRole, set[PermissionCode]] = {
    SystemRole.ADMIN: set(PermissionCode),
    SystemRole.IT_OPERATOR: {
        PermissionCode.DOCUMENT_READ,
        PermissionCode.DOCUMENT_WRITE,
        PermissionCode.DOCUMENT_UPLOAD,
        PermissionCode.DOCUMENT_UPDATE,
        PermissionCode.DOCUMENT_REINDEX,
        PermissionCode.SYSTEM_READ,
        PermissionCode.SYSTEM_EXECUTE,
        PermissionCode.REPORT_GENERATE,
        PermissionCode.USER_READ,
        PermissionCode.AI_EXECUTE,
        PermissionCode.AI_READ,
        PermissionCode.AUDIT_READ,
    },
    SystemRole.SECURITY_ANALYST: {
        PermissionCode.DOCUMENT_READ,
        PermissionCode.SECURITY_READ,
        PermissionCode.SECURITY_EXECUTE,
        PermissionCode.REPORT_GENERATE,
        PermissionCode.AUDIT_READ,
        PermissionCode.AI_READ,
        PermissionCode.AI_EXECUTE,
    },
    SystemRole.MANAGER: {
        PermissionCode.DOCUMENT_READ,
        PermissionCode.DOCUMENT_WRITE,
        PermissionCode.DOCUMENT_UPLOAD,
        PermissionCode.DOCUMENT_UPDATE,
        PermissionCode.SYSTEM_READ,
        PermissionCode.REPORT_GENERATE,
        PermissionCode.APPROVAL_APPROVE,
        PermissionCode.USER_READ,
        PermissionCode.AI_EXECUTE,
        PermissionCode.AI_READ,
    },
    SystemRole.GENERAL_EMPLOYEE: {
        PermissionCode.DOCUMENT_READ,
        PermissionCode.AI_EXECUTE,
        PermissionCode.AI_READ,
    },
}


def get_permission_resource_action(codename: str) -> tuple[str, str]:
    """Split a 'resource.action' codename into (resource, action)."""
    parts = codename.split(".", maxsplit=1)
    if len(parts) != 2:
        msg = f"Invalid permission codename: {codename!r}"
        raise ValueError(msg)
    return parts[0], parts[1]
