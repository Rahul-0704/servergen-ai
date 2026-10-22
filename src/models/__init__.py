"""
ServerGen AI — Model Registry.

Imports all ORM models so that Alembic and SQLAlchemy metadata discovery
can find them. Every new model MUST be imported here.
"""

from src.models.approval import ApprovalRequest
from src.models.audit import AuditEvent
from src.models.base import Base
from src.models.role import Permission, Role, RolePermission
from src.models.session import RefreshSession
from src.models.user import User

__all__ = [
    "ApprovalRequest",
    "AuditEvent",
    "Base",
    "Permission",
    "RefreshSession",
    "Role",
    "RolePermission",
    "User",
]
