"""
ServerGen AI — User Repository.

Data access for User model. All database queries are centralized here.
No business logic — that belongs in the service layer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.role import Role
from src.models.user import User


class UserRepository:
    """Repository for User data access operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Get user by ID with role and permissions eagerly loaded."""
        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.role).selectinload(Role.permissions))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        """Get user by username with role and permissions eagerly loaded."""
        stmt = (
            select(User)
            .where(User.username == username)
            .options(selectinload(User.role).selectinload(Role.permissions))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Get user by email."""
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 50,
        active_only: bool = False,
        role_id: uuid.UUID | None = None,
    ) -> list[User]:
        """List users with optional active and role filter, and pagination."""
        stmt = select(User).options(selectinload(User.role))
        if active_only:
            stmt = stmt.where(User.is_active.is_(True))
        if role_id is not None:
            stmt = stmt.where(User.role_id == role_id)
        stmt = stmt.order_by(User.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_users(self, active_only: bool = False, role_id: uuid.UUID | None = None) -> int:
        """Count users with optional filters."""
        stmt = select(func.count()).select_from(User)
        if active_only:
            stmt = stmt.where(User.is_active.is_(True))
        if role_id is not None:
            stmt = stmt.where(User.role_id == role_id)
        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def create(self, user: User) -> User:
        """Insert a new user."""
        self.db.add(user)
        await self.db.flush()
        return user

    async def increment_failed_logins(self, user_id: uuid.UUID) -> None:
        """Increment failed login counter by 1."""
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(failed_login_attempts=User.failed_login_attempts + 1)
        )
        await self.db.execute(stmt)

    async def reset_failed_logins(self, user_id: uuid.UUID) -> None:
        """Reset failed login counter and clear lock."""
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(failed_login_attempts=0, locked_until=None)
        )
        await self.db.execute(stmt)

    async def lock_account(self, user_id: uuid.UUID, until: datetime) -> None:
        """Lock a user account until the specified time."""
        stmt = update(User).where(User.id == user_id).values(locked_until=until)
        await self.db.execute(stmt)

    async def update_last_login(self, user_id: uuid.UUID) -> None:
        """Record last login timestamp."""
        stmt = update(User).where(User.id == user_id).values(last_login=datetime.now(UTC))
        await self.db.execute(stmt)

    async def disable_user(self, user_id: uuid.UUID) -> None:
        """Disable a user account."""
        stmt = update(User).where(User.id == user_id).values(is_active=False)
        await self.db.execute(stmt)

    async def enable_user(self, user_id: uuid.UUID) -> None:
        """Enable a user account."""
        stmt = update(User).where(User.id == user_id).values(is_active=True)
        await self.db.execute(stmt)
