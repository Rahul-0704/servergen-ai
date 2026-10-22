"""
ServerGen AI — Approval Schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApprovalActionRequest(BaseModel):
    """Optional reviewer notes for approve/reject."""

    notes: str = Field(default="", max_length=1000)


class ApprovalResponse(BaseModel):
    """An approval request as exposed to clients (no raw operation payload)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    request_id: str
    requester_user_id: uuid.UUID
    requester_role: str
    operation_summary: str
    operation_fingerprint: str
    status: str
    risk_assessment_json: dict[str, Any] | None = None
    task_classification_json: dict[str, Any] | None = None
    reviewer_user_id: uuid.UUID | None = None
    reviewer_notes: str | None = None
    created_at: datetime
    expires_at: datetime
    resolved_at: datetime | None = None
    consumed_at: datetime | None = None


class ApprovalPage(BaseModel):
    """Paginated approvals."""

    items: list[ApprovalResponse]
    total: int
    skip: int
    limit: int
