"""
ServerGen AI — Refresh Session Model.

Stores hashed refresh tokens (never plaintext) with rotation tracking,
revocation support, and expiration.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, generate_uuid


class RefreshSession(Base):
    """
    Refresh token session. Tokens are stored as SHA-256 hashes — never plaintext.

    Supports rotation tracking via replaced_by, and revocation via revoked flag.
    """

    __tablename__ = "refresh_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=generate_uuid
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    family_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        comment="Token family for rotation reuse detection",
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        default=None,
        comment="ID of the session that replaced this one during rotation",
    )
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    def __repr__(self) -> str:
        return f"<RefreshSession(user_id={self.user_id}, revoked={self.revoked})>"
