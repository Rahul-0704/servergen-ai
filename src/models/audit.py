"""
ServerGen AI — Audit Event Model (Tamper-Evident AI Activity Ledger).

Each event is hash-chained to the previous event using SHA-256.
This is a tamper-evident mechanism that detects modification — it is NOT
described as tamper-proof, blockchain, or immutable.

Hash computation: SHA-256(canonical_json(event_data) + previous_hash)
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, generate_uuid


class AuditEvent(Base):
    """
    Tamper-Evident AI Activity Ledger entry.

    Each event contains a hash computed from its canonical data plus the
    previous event's hash, forming a detectable chain. Integrity verification
    walks the chain and detects any broken links.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('allow','deny','require_approval','error')",
            name="ck_audit_decision",
        ),
        CheckConstraint(
            "risk_level IN ('low','medium','high','critical')",
            name="ck_audit_risk_level",
        ),
        Index("ix_audit_events_type_timestamp", "event_type", "timestamp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=generate_uuid
    )
    sequence_number: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        nullable=False,
        index=True,
        comment="Monotonically increasing sequence for chain ordering",
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        index=True,
    )

    # Who
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # What
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Category: auth, agent, tool, policy, user, approval, system",
    )
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Specific action: login_success, login_failure, execution_started, etc.",
    )
    resource: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Decision
    decision: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="allow",
        comment="allow, deny, require_approval",
    )
    risk_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="low",
        comment="low, medium, high, critical",
    )

    # AI context
    agent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Extra data (structured, no secrets)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Hash chain
    previous_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 hash of the previous event (null for first event)",
    )
    event_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256(canonical_json(event_data) + previous_hash)",
    )

    def __repr__(self) -> str:
        return (
            f"<AuditEvent(seq={self.sequence_number}, "
            f"type={self.event_type!r}, action={self.action!r})>"
        )
