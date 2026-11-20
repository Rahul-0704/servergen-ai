"""
ServerGen AI — Notification Repository.

Provides database access operations for notifications and user preferences.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.notification import Notification, NotificationPreference


class NotificationRepository:
    """Repository handling persistence for notifications and preferences."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, notification: Notification) -> Notification:
        """Persist a single notification."""
        self.db.add(notification)
        await self.db.flush()
        return notification

    async def bulk_create(self, notifications: list[Notification]) -> list[Notification]:
        """Persist multiple notifications."""
        self.db.add_all(notifications)
        await self.db.flush()
        return notifications

    async def get_by_id(self, notification_id: uuid.UUID) -> Notification | None:
        """Fetch a notification by ID."""
        stmt = select(Notification).where(Notification.id == notification_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Notification], int]:
        """List notifications for a user with total count."""
        conditions = [Notification.recipient_user_id == user_id]
        if unread_only:
            conditions.append(Notification.is_read.is_(False))

        count_stmt = select(func.count()).select_from(Notification).where(*conditions)
        total = (await self.db.execute(count_stmt)).scalar_one()

        stmt = (
            select(Notification)
            .where(*conditions)
            .order_by(Notification.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all()), total

    async def count_unread(self, user_id: uuid.UUID) -> int:
        """Count unread notifications for a user."""
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.recipient_user_id == user_id,
                Notification.is_read.is_(False),
            )
        )
        return (await self.db.execute(stmt)).scalar_one()

    async def mark_as_read(
        self, notification_id: uuid.UUID, user_id: uuid.UUID
    ) -> Notification | None:
        """Mark a specific notification as read ensuring recipient ownership."""
        now = datetime.now(UTC)
        stmt = (
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.recipient_user_id == user_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True, read_at=now)
            .returning(Notification)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        """Mark all notifications as read for a user."""
        now = datetime.now(UTC)
        stmt = (
            update(Notification)
            .where(
                Notification.recipient_user_id == user_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True, read_at=now)
        )
        result = await self.db.execute(stmt)
        return result.rowcount or 0

    async def get_preferences(self, user_id: uuid.UUID) -> NotificationPreference | None:
        """Fetch notification preferences for a user."""
        stmt = select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_preferences(
        self,
        user_id: uuid.UUID,
        approvals_enabled: bool = True,
        documents_enabled: bool = True,
        analytics_enabled: bool = True,
        system_enabled: bool = True,
    ) -> NotificationPreference:
        """Upsert notification preferences for a user (security is always mandatory)."""
        prefs = await self.get_preferences(user_id)
        if not prefs:
            prefs = NotificationPreference(
                user_id=user_id,
                approvals_enabled=approvals_enabled,
                documents_enabled=documents_enabled,
                security_enabled=True,
                analytics_enabled=analytics_enabled,
                system_enabled=system_enabled,
            )
            self.db.add(prefs)
        else:
            prefs.approvals_enabled = approvals_enabled
            prefs.documents_enabled = documents_enabled
            prefs.security_enabled = True  # Always enforced
            prefs.analytics_enabled = analytics_enabled
            prefs.system_enabled = system_enabled

        await self.db.flush()
        return prefs
