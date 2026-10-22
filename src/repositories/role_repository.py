"""
ServerGen AI — Role & Permission Repository.

Data access for Role and Permission models. Used for seeding and
admin operations. Runtime RBAC uses in-memory mappings for speed.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.role import Permission, Role, RolePermission


class RoleRepository:
    """Repository for Role data access operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, role_id: uuid.UUID) -> Role | None:
        """Get a role by ID with permissions eagerly loaded."""
        stmt = select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Role | None:
        """Get a role by name with permissions eagerly loaded."""
        stmt = select(Role).where(Role.name == name).options(selectinload(Role.permissions))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_roles(self) -> list[Role]:
        """List all roles with their permissions."""
        stmt = select(Role).options(selectinload(Role.permissions))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, role: Role) -> Role:
        """Insert a new role."""
        self.db.add(role)
        await self.db.flush()
        return role

    async def get_or_create_permission(
        self, codename: str, resource: str, action: str
    ) -> Permission:
        """Get an existing permission by codename, or create it."""
        stmt = select(Permission).where(Permission.codename == codename)
        result = await self.db.execute(stmt)
        perm = result.scalar_one_or_none()
        if perm is None:
            perm = Permission(
                id=uuid.uuid4(),
                codename=codename,
                description=f"{resource}.{action}",
                resource=resource,
                action=action,
            )
            self.db.add(perm)
            await self.db.flush()
        return perm

    async def assign_permission(self, role_id: uuid.UUID, permission_id: uuid.UUID) -> None:
        """Assign a permission to a role (idempotent)."""
        stmt = select(RolePermission).where(
            RolePermission.role_id == role_id,
            RolePermission.permission_id == permission_id,
        )
        result = await self.db.execute(stmt)
        if result.scalar_one_or_none() is None:
            rp = RolePermission(role_id=role_id, permission_id=permission_id)
            self.db.add(rp)
            await self.db.flush()
