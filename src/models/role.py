"""
ServerGen AI — Role, Permission, and RolePermission Models.

Implements the RBAC data model with roles, permissions (codename-based),
and a many-to-many mapping between them.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from src.models.user import User


class Role(TimestampMixin, Base):
    """
    RBAC role. Each user has exactly one role.

    System roles: administrator, it_operator, security_analyst, manager, general_employee.
    """

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=generate_uuid
    )
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    permissions: Mapped[list[Permission]] = relationship(
        "Permission",
        secondary="role_permissions",
        back_populates="roles",
        lazy="selectin",
    )
    users: Mapped[list[User]] = relationship("User", back_populates="role", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Role(name={self.name!r})>"


class Permission(Base):
    """
    Individual permission identified by a codename (e.g., 'users:read').

    Permissions are assigned to roles, not directly to users.
    """

    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=generate_uuid
    )
    codename: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    resource: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)

    # Relationships
    roles: Mapped[list[Role]] = relationship(
        "Role",
        secondary="role_permissions",
        back_populates="permissions",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Permission(codename={self.codename!r})>"


class RolePermission(Base):
    """Many-to-many mapping between roles and permissions."""

    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )
