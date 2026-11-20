"""
ServerGen AI — Natural Language Data Analysis History Model.

Persists analytical audit queries, execution status, and result metadata
without unnecessarily duplicating sensitive spreadsheet cell contents.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, generate_uuid


class AnalysisHistory(Base):
    """
    Historical log of natural language data analysis questions and results.
    """

    __tablename__ = "analysis_history"
    __table_args__ = (
        Index("ix_analysis_history_user_created", "user_id", "created_at"),
        Index("ix_analysis_history_doc_created", "document_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=generate_uuid
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sheet_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="statistical",
        comment="statistical, ranking, groupby, financial, quality, trend, overview",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="success", comment="success, failed, rejected"
    )
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    user: Mapped[Any] = relationship("User", foreign_keys=[user_id], lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<AnalysisHistory(id={self.id}, user={self.user_id}, "
            f"type={self.analysis_type!r}, status={self.status!r})>"
        )
