"""
ServerGen AI — Audit API Routes.

GET /api/v1/audit/events      — list audit events (paginated, filtered)
GET /api/v1/audit/events/{id} — get a single audit event
GET /api/v1/audit/verify      — verify hash chain integrity
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.permissions import PermissionCode
from src.auth.rbac import require_permission
from src.core.database import get_db
from src.repositories.audit_repository import AuditFilters
from src.schemas.audit import AuditChainVerification, AuditEventPage, AuditEventResponse
from src.services.audit_service import AuditService

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])

_audit_read = require_permission(PermissionCode.AUDIT_READ)

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get(
    "",
    response_model=AuditEventPage,
    dependencies=[Depends(_audit_read)],
)
@router.get(
    "/events",
    response_model=AuditEventPage,
    dependencies=[Depends(_audit_read)],
)
async def list_events(
    db: DbDep,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    event_type: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    decision: str | None = Query(default=None),
    risk_level: str | None = Query(default=None),
    request_id: str | None = Query(default=None),
) -> AuditEventPage:
    """List audit events in chain order. Requires audit.read permission."""
    svc = AuditService(db)
    filters = AuditFilters(
        event_type=event_type,
        user_id=user_id,
        decision=decision,
        risk_level=risk_level,
        request_id=request_id,
    )
    events = await svc.repo.list_events(skip=skip, limit=limit, filters=filters)
    total = await svc.repo.count_events(filters=filters)
    return AuditEventPage(
        items=[AuditEventResponse.model_validate(e) for e in events],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/verify",
    response_model=AuditChainVerification,
    dependencies=[Depends(_audit_read)],
)
@router.post(
    "/verify-integrity",
    response_model=AuditChainVerification,
    dependencies=[Depends(_audit_read)],
)
async def verify_chain(db: DbDep) -> AuditChainVerification:
    """
    Verify the Tamper-Evident AI Activity Ledger hash chain integrity.

    Walks the entire chain using batched iteration.
    """
    svc = AuditService(db)
    report = await svc.verify_integrity()
    return AuditChainVerification(
        status=report.status,
        events_checked=report.events_checked,
        broken_at_sequence=report.broken_at_sequence,
        reason=report.reason,
    )


@router.get(
    "/{event_id}",
    response_model=AuditEventResponse,
    dependencies=[Depends(_audit_read)],
)
@router.get(
    "/events/{event_id}",
    response_model=AuditEventResponse,
    dependencies=[Depends(_audit_read)],
)
async def get_event(event_id: uuid.UUID, db: DbDep) -> AuditEventResponse:
    """Get a single audit event by ID."""
    from src.core.exceptions import NotFoundError

    svc = AuditService(db)
    event = await svc.repo.get_by_id(event_id)
    if event is None:
        raise NotFoundError(f"Audit event {event_id} not found")
    return AuditEventResponse.model_validate(event)
