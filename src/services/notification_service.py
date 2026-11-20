"""
ServerGen AI — Automated Notification Service.

Coordinates event-driven notifications across approvals, documents, security,
and analytics with role-based recipient resolution, duplicate suppression,
and user preferences.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.notification import Notification, NotificationPreference
from src.models.role import Role
from src.models.user import User
from src.repositories.notification_repository import NotificationRepository

logger = logging.getLogger("servergen.services.notification")


class NotificationService:
    """Service orchestrating event-driven notifications across the enterprise."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = NotificationRepository(db)

    async def notify_user(
        self,
        recipient_user_id: uuid.UUID | str,
        event_type: str,
        title: str,
        message: str,
        related_resource_type: str | None = None,
        related_resource_id: str | None = None,
        priority: str = "medium",
    ) -> Notification | None:
        """
        Deliver a notification to a specific user, checking preferences
        and preventing duplicate spam.
        """
        uid = (
            recipient_user_id
            if isinstance(recipient_user_id, uuid.UUID)
            else uuid.UUID(str(recipient_user_id))
        )

        # 1. Check user preferences (security notifications are mandatory)
        prefs = await self.repo.get_preferences(uid)
        if prefs:
            if event_type.startswith("approval_") and not prefs.approvals_enabled:
                return None
            if event_type.startswith("document_") and not prefs.documents_enabled:
                return None
            if event_type.startswith("analytics_") and not prefs.analytics_enabled:
                return None
            if event_type.startswith("system_") and not prefs.system_enabled:
                return None

        # 2. Duplicate suppression (same recipient, event_type, resource within 30s)
        recent_cutoff = datetime.now(UTC) - timedelta(seconds=30)
        stmt_dup = select(Notification).where(
            Notification.recipient_user_id == uid,
            Notification.event_type == event_type,
            Notification.related_resource_id == related_resource_id,
            Notification.created_at >= recent_cutoff,
        )
        existing = (await self.db.execute(stmt_dup)).scalar_one_or_none()
        if existing:
            logger.debug("Suppressed duplicate notification %s for user %s", event_type, uid)
            return existing

        # 3. Create notification
        valid_priorities = ("low", "medium", "high", "urgent")
        clean_priority = priority.lower() if priority.lower() in valid_priorities else "medium"
        notification = Notification(
            id=uuid.uuid4(),
            recipient_user_id=uid,
            event_type=event_type,
            title=title,
            message=message,
            related_resource_type=related_resource_type,
            related_resource_id=related_resource_id,
            priority=clean_priority,
            is_read=False,
            created_at=datetime.now(UTC),
        )
        created = await self.repo.create(notification)
        logger.info("Notification sent to user %s [%s]: %s", uid, event_type, title)
        return created

    async def notify_role(
        self,
        role_name: str,
        event_type: str,
        title: str,
        message: str,
        related_resource_type: str | None = None,
        related_resource_id: str | None = None,
        priority: str = "medium",
        exclude_user_id: uuid.UUID | str | None = None,
    ) -> list[Notification]:
        """
        Deliver a notification to all active users with a specified role
        (e.g., all managers or administrators).
        """
        exclude_uid = (
            uuid.UUID(str(exclude_user_id)) if exclude_user_id else None
        )

        stmt = (
            select(User)
            .join(Role, User.role_id == Role.id)
            .where(
                Role.name == role_name,
                User.is_active.is_(True),
            )
        )
        if exclude_uid:
            stmt = stmt.where(User.id != exclude_uid)

        result = await self.db.execute(stmt)
        users = list(result.scalars().all())

        notifications = []
        for u in users:
            n = await self.notify_user(
                recipient_user_id=u.id,
                event_type=event_type,
                title=title,
                message=message,
                related_resource_type=related_resource_type,
                related_resource_id=related_resource_id,
                priority=priority,
            )
            if n:
                notifications.append(n)

        return notifications

    async def list_for_user(
        self,
        user_id: uuid.UUID | str,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Notification], int]:
        """Retrieve paginated notifications for a user."""
        uid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
        return await self.repo.list_for_user(
            uid, unread_only=unread_only, limit=limit, offset=offset
        )

    async def get_unread_count(self, user_id: uuid.UUID | str) -> int:
        """Get the total count of unread notifications for a user."""
        uid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
        return await self.repo.count_unread(uid)

    async def mark_as_read(
        self, notification_id: uuid.UUID | str, user_id: uuid.UUID | str
    ) -> Notification | None:
        """Mark a single notification as read if owned by the user."""
        nid = (
            notification_id
            if isinstance(notification_id, uuid.UUID)
            else uuid.UUID(str(notification_id))
        )
        uid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
        return await self.repo.mark_as_read(nid, uid)

    async def mark_all_as_read(self, user_id: uuid.UUID | str) -> int:
        """Mark all notifications as read for the user."""
        uid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
        return await self.repo.mark_all_read(uid)

    async def get_preferences(self, user_id: uuid.UUID | str) -> NotificationPreference:
        """Get or initialize default notification preferences."""
        uid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
        prefs = await self.repo.get_preferences(uid)
        if not prefs:
            prefs = await self.repo.upsert_preferences(uid)
        return prefs

    async def update_preferences(
        self,
        user_id: uuid.UUID | str,
        approvals_enabled: bool = True,
        documents_enabled: bool = True,
        analytics_enabled: bool = True,
        system_enabled: bool = True,
    ) -> NotificationPreference:
        """Update notification preferences."""
        uid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
        return await self.repo.upsert_preferences(
            user_id=uid,
            approvals_enabled=approvals_enabled,
            documents_enabled=documents_enabled,
            analytics_enabled=analytics_enabled,
            system_enabled=system_enabled,
        )
