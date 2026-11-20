"""
ServerGen AI — Automated Notifications Model.

Persists event-driven notifications for authorized users with priority,
resource linkage, read tracking, and user notification preferences.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, generate_uuid


class Notification(Base):
    """
    Event-driven notification record persisted in the database.

    Recipients can view only their own notifications.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'urgent')",
            name="ck_notifications_priority",
        ),
        Index("ix_notifications_user_read_created", "recipient_user_id", "is_read", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=generate_uuid
    )
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="e.g. approval_required, approval_decision, document_indexed, security_alert",
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    related_resource_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="approval, document, spreadsheet, security"
    )
    related_resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # Relationships
    user: Mapped[Any] = relationship("User", foreign_keys=[recipient_user_id], lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<Notification(id={self.id}, user={self.recipient_user_id}, "
            f"type={self.event_type!r}, read={self.is_read})>"
        )


class NotificationPreference(Base):
    """
    User-configurable notification channel preferences.

    Security notifications are mandatory and cannot be disabled by policy.
    """

    __tablename__ = "notification_preferences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=generate_uuid
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    approvals_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    documents_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    security_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )  # Policy enforced
    analytics_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    system_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<NotificationPreference(user={self.user_id})>"
