"""
ServerGen AI — Automated Notifications REST API.

Provides endpoints for:
- Fetching user notifications with pagination and unread filtering
- Checking unread notification counts
- Marking individual or all notifications as read
- Managing user notification preferences
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.rbac import AuthContext, get_auth_context
from src.core.database import get_db
from src.services.notification_service import NotificationService

logger = logging.getLogger("servergen.api.notifications")

router = APIRouter(prefix="/api/v1/notifications", tags=["Automated Notifications"])


# ── Schemas ─────────────────────────────────────────────────────────────────


class NotificationResponse(BaseModel):
    id: str
    recipient_user_id: str
    event_type: str
    category: str = "system"
    title: str
    message: str
    related_resource_type: str | None = None
    related_resource_id: str | None = None
    priority: str
    is_read: bool
    created_at: str
    read_at: str | None = None


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    unread_count: int


class UnreadCountResponse(BaseModel):
    unread_count: int


class UpdatePreferencesRequest(BaseModel):
    approvals_enabled: bool = True
    documents_enabled: bool = True
    analytics_enabled: bool = True
    system_enabled: bool = True


class PreferencesResponse(BaseModel):
    user_id: str
    approvals_enabled: bool
    documents_enabled: bool
    security_enabled: bool
    analytics_enabled: bool
    system_enabled: bool


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    unread_only: bool = Query(False, description="Filter to only unread notifications"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List paginated notifications for the authenticated user."""
    svc = NotificationService(db)
    items, total = await svc.list_for_user(
        user_id=auth.user_id,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )
    unread_cnt = await svc.get_unread_count(auth.user_id)

    def _to_category(event_type: str, resource_type: str | None) -> str:
        et = (event_type or "").lower()
        rt = (resource_type or "").lower()
        if "approval" in et or "approval" in rt:
            return "approval"
        if "document" in et or "document" in rt:
            return "document"
        if "security" in et or "denied" in et or "risk" in et:
            return "security"
        if "analytics" in et or "spreadsheet" in et or "spreadsheet" in rt:
            return "analytics"
        return "system"

    return {
        "items": [
            {
                "id": str(n.id),
                "recipient_user_id": str(n.recipient_user_id),
                "event_type": n.event_type,
                "category": _to_category(n.event_type, n.related_resource_type),
                "title": n.title,
                "message": n.message,
                "related_resource_type": n.related_resource_type,
                "related_resource_id": n.related_resource_id,
                "priority": n.priority,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else "",
                "read_at": n.read_at.isoformat() if n.read_at else None,
            }
            for n in items
        ],
        "total": total,
        "unread_count": unread_cnt,
    }


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Get the current unread notifications count for the active user."""
    svc = NotificationService(db)
    cnt = await svc.get_unread_count(auth.user_id)
    return {"unread_count": cnt}


@router.patch("/{notification_id}/read")
async def mark_notification_as_read(
    notification_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Mark a notification as read if owned by the current user."""
    svc = NotificationService(db)
    notif = await svc.mark_as_read(notification_id=notification_id, user_id=auth.user_id)
    if not notif:
        # Check if notification exists but belongs to someone else
        existing = await svc.repo.get_by_id(notification_id)
        if existing and str(existing.recipient_user_id) != str(auth.user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify notifications belonging to another user.",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found or already marked as read.",
        )

    await db.commit()
    return {
        "status": "success",
        "notification_id": str(notif.id),
        "is_read": True,
        "read_at": notif.read_at.isoformat() if notif.read_at else None,
    }


@router.patch("/read-all")
@router.post("/read-all")
async def mark_all_notifications_as_read(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Mark all unread notifications as read for the authenticated user."""
    svc = NotificationService(db)
    count = await svc.mark_all_as_read(auth.user_id)
    await db.commit()
    return {"status": "success", "marked_read": count}


@router.get("/preferences", response_model=PreferencesResponse)
async def get_preferences(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve the current user's notification preferences."""
    svc = NotificationService(db)
    prefs = await svc.get_preferences(auth.user_id)
    return {
        "user_id": str(prefs.user_id),
        "approvals_enabled": prefs.approvals_enabled,
        "documents_enabled": prefs.documents_enabled,
        "security_enabled": True,  # Mandatory
        "analytics_enabled": prefs.analytics_enabled,
        "system_enabled": prefs.system_enabled,
    }


@router.put("/preferences", response_model=PreferencesResponse)
async def update_preferences(
    body: UpdatePreferencesRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update notification preferences for the current user."""
    svc = NotificationService(db)
    prefs = await svc.update_preferences(
        user_id=auth.user_id,
        approvals_enabled=body.approvals_enabled,
        documents_enabled=body.documents_enabled,
        analytics_enabled=body.analytics_enabled,
        system_enabled=body.system_enabled,
    )
    await db.commit()
    return {
        "user_id": str(prefs.user_id),
        "approvals_enabled": prefs.approvals_enabled,
        "documents_enabled": prefs.documents_enabled,
        "security_enabled": True,
        "analytics_enabled": prefs.analytics_enabled,
        "system_enabled": prefs.system_enabled,
    }
