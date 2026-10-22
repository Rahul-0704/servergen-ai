"""
ServerGen AI — Audit Schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditEventResponse(BaseModel):
    """A single ledger entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sequence_number: int
    timestamp: datetime
    user_id: str | None = None
    role: str | None = None
    request_id: str
    event_type: str
    action: str
    resource: str | None = None
    decision: str
    risk_level: str
    agent: str | None = None
    model: str | None = None
    tool: str | None = None
    metadata_json: dict[str, Any] | None = None
    previous_hash: str | None = None
    event_hash: str


class AuditEventPage(BaseModel):
    """Paginated audit events."""

    items: list[AuditEventResponse]
    total: int
    skip: int
    limit: int


class AuditChainVerification(BaseModel):
    """Result of a Tamper-Evident AI Activity Ledger verification."""

    status: str
    events_checked: int
    broken_at_sequence: int | None = None
    reason: str = ""
