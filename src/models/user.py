"""
ServerGen AI — User Model.

Stores user accounts with Argon2id-hashed passwords, role assignment,
account lockout tracking, and activation status.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, generate_uuid
from src.models.role import Role


class User(TimestampMixin, Base):
    """
    User account. Passwords are stored as Argon2id hashes — never plaintext.

    Account lockout is tracked via failed_login_attempts and locked_until.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("failed_login_attempts >= 0", name="ck_users_failed_attempts_nonneg"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=generate_uuid
    )
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    # Role assignment
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False
    )
    role: Mapped[Role] = relationship("Role", back_populates="users", lazy="selectin")

    # Account status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Login security
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    def __repr__(self) -> str:
        return f"<User(username={self.username!r}, role_id={self.role_id})>"
