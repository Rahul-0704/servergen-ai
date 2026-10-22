"""
ServerGen AI — Approval Request Model.

Backend approval workflow for HIGH/CRITICAL operations.

SECURITY MODEL
- A PENDING approval never executes anything.
- ``operation_payload`` stores the exact (non-secret) operation that was
  requested; ``operation_fingerprint`` binds the approval to it. On resume the
  operation is rebuilt from the payload, re-fingerprinted and compared.
- ``consumed_at`` makes an approval single-use (set atomically before execution).
- Separation of duties (requester != reviewer) is enforced in the service layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, generate_uuid


class ApprovalRequest(Base):
    """Approval request for operations that require human authorization."""

    __tablename__ = "approval_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected','expired','cancelled')",
            name="ck_approval_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=generate_uuid
    )
    request_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        comment="Correlation ID to the originating orchestration request",
    )

    # Requester
    requester_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    requester_role: Mapped[str] = mapped_column(String(50), nullable=False)

    # Operation details
    operation_summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Human-readable description of the operation requiring approval",
    )
    task_classification_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    risk_assessment_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    operation_payload: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Exact operation to resume after approval (no credentials/secrets)",
    )
    operation_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hash of security-relevant operation attributes",
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
        comment="pending, approved, rejected, expired, cancelled",
    )

    # Reviewer
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Set (atomically) when the approved operation is executed — single use",
    )

    def __repr__(self) -> str:
        return f"<ApprovalRequest(id={self.id}, status={self.status!r})>"
