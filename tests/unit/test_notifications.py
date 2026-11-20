"""
ServerGen AI — Automated Notifications Test Suite.

Verifies:
1. Event-driven notification generation and database persistence
2. Role-based recipient resolution (managers receive approval alerts)
3. Requester notifications upon approval or rejection
4. Strict multi-tenant user isolation (User A cannot view or mark User B's alerts)
5. Read state tracking (mark as read, mark all read, unread counts)
6. Duplicate event suppression
7. User notification preferences (security alerts remain mandatory)
8. REST API endpoints (/api/v1/notifications, /unread-count, /read, /read-all, /preferences)
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.ai.schemas import OperationContext, RiskAssessment
from src.app import create_app
from src.core.database import get_db
from src.core.security import create_access_token, hash_password
from src.models.role import Role
from src.models.user import User
from src.services.approval_service import ApprovalService
from src.services.notification_service import NotificationService


async def _create_user(
    db: AsyncSession, role_name: str, username_prefix: str = "user"
) -> tuple[User, str]:
    """Helper to create a user with a given role and return (user, jwt_token)."""
    res = await db.execute(select(Role).where(Role.name == role_name))
    role_entity = res.scalar_one_or_none()
    if not role_entity:
        role_entity = Role(
            id=uuid.uuid4(),
            name=role_name,
            description=f"Role {role_name}",
            permissions=[],
        )
        db.add(role_entity)
        await db.flush()

    user = User(
        id=uuid.uuid4(),
        username=f"{username_prefix}_{uuid.uuid4().hex[:6]}",
        email=f"{username_prefix}_{uuid.uuid4().hex[:6]}@servergen.local",
        hashed_password=hash_password("Pass1!Secure"),
        role_id=role_entity.id,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    token = create_access_token(user_id=str(user.id), role=role_name)
    return user, token


@pytest.mark.anyio
async def test_notification_service_creation_and_unread_count(db_session: AsyncSession):
    """Verify notification persistence and unread count tracking."""
    user, _ = await _create_user(db_session, "general_employee")
    svc = NotificationService(db_session)

    # Initially 0 unread
    cnt0 = await svc.get_unread_count(user.id)
    assert cnt0 == 0

    # Create 2 notifications
    n1 = await svc.notify_user(
        recipient_user_id=user.id,
        event_type="document_indexed",
        title="Doc 1 Ready",
        message="Your document has been indexed.",
        priority="low",
    )
    n2 = await svc.notify_user(
        recipient_user_id=user.id,
        event_type="analytics_completed",
        title="Analysis Done",
        message="Spreadsheet analysis has finished.",
        priority="medium",
    )
    await db_session.commit()

    assert n1 is not None
    assert n2 is not None

    cnt2 = await svc.get_unread_count(user.id)
    assert cnt2 == 2

    # Mark n1 as read
    res_read = await svc.mark_as_read(n1.id, user.id)
    await db_session.commit()
    assert res_read is not None
    assert res_read.is_read is True
    assert res_read.read_at is not None

    # Unread should now be 1
    cnt1 = await svc.get_unread_count(user.id)
    assert cnt1 == 1

    # Mark all read
    marked = await svc.mark_all_as_read(user.id)
    await db_session.commit()
    assert marked == 1

    cnt_final = await svc.get_unread_count(user.id)
    assert cnt_final == 0


@pytest.mark.anyio
async def test_notification_duplicate_suppression(db_session: AsyncSession):
    """Verify that identical notifications within 30 seconds are suppressed."""
    user, _ = await _create_user(db_session, "general_employee")
    svc = NotificationService(db_session)

    n1 = await svc.notify_user(
        recipient_user_id=user.id,
        event_type="security_alert",
        title="Brute Force Attempt",
        message="Suspicious activity detected.",
        related_resource_type="security",
        related_resource_id="req-12345",
        priority="high",
    )
    await db_session.commit()
    assert n1 is not None

    # Immediate second call with identical parameters
    n2 = await svc.notify_user(
        recipient_user_id=user.id,
        event_type="security_alert",
        title="Brute Force Attempt",
        message="Suspicious activity detected.",
        related_resource_type="security",
        related_resource_id="req-12345",
        priority="high",
    )
    # Returns existing notification without creating duplicate
    assert n2.id == n1.id

    cnt = await svc.get_unread_count(user.id)
    assert cnt == 1


@pytest.mark.anyio
async def test_approval_lifecycle_notifications(db_session: AsyncSession):
    """
    Verify event-driven notifications during approval lifecycle:
    1. Employee creates high-risk request -> Manager receives 'approval_required' notification.
    2. Manager approves request -> Employee receives 'approval_decision' notification.
    """
    mgr, _ = await _create_user(db_session, "manager", "mgr")
    emp, _ = await _create_user(db_session, "general_employee", "emp")

    appr_svc = ApprovalService(db_session)
    notif_svc = NotificationService(db_session)

    context = OperationContext(
        user_id=str(emp.id),
        role="general_employee",
        task_category="operations",
        operation_type="execute",
        resource="server-prod-01",
        permission="deploy.execute",
    )
    risk = RiskAssessment(
        risk_level="high",
        requires_approval=True,
        factors=["production_impact"],
    )

    # 1. Employee creates approval request
    req = await appr_svc.create(
        request_id=f"req-{uuid.uuid4().hex[:8]}",
        context=context,
        risk=risk,
        operation_summary="Deploy critical hotfix to production cluster",
    )
    await db_session.commit()

    # Manager should have received approval_required notification
    mgr_notifs, total_mgr = await notif_svc.list_for_user(mgr.id)
    assert total_mgr >= 1
    approval_notif = next((n for n in mgr_notifs if n.event_type == "approval_required"), None)
    assert approval_notif is not None
    assert str(req.id) in (approval_notif.related_resource_id or "")

    # 2. Manager approves request
    await appr_svc.approve(
        approval_id=req.id,
        reviewer_user_id=str(mgr.id),
        reviewer_role="manager",
        notes="Authorized for release",
    )
    await db_session.commit()

    # Employee should have received approval_decision notification
    emp_notifs, total_emp = await notif_svc.list_for_user(emp.id)
    assert total_emp >= 1
    decision_notif = next((n for n in emp_notifs if n.event_type == "approval_decision"), None)
    assert decision_notif is not None
    assert "approved" in decision_notif.message.lower()


@pytest.mark.anyio
async def test_notification_user_isolation(db_session: AsyncSession):
    """
    Verify security isolation:
    User A cannot view, access, or mark as read User B's private notifications.
    """
    user_a, token_a = await _create_user(db_session, "general_employee", "alice")
    user_b, token_b = await _create_user(db_session, "general_employee", "bob")

    notif_svc = NotificationService(db_session)

    # Create notification for User A
    notif_a = await notif_svc.notify_user(
        recipient_user_id=user_a.id,
        event_type="document_indexed",
        title="Alice's Private Document",
        message="Confidential analysis ready.",
    )
    await db_session.commit()

    app = create_app()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # User B queries their notifications -> Should be empty (0 items)
        res_b = await client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert res_b.status_code == 200
        assert res_b.json()["total"] == 0

        # User B attempts to mark User A's notification as read -> 403 Forbidden
        res_hack = await client.patch(
            f"/api/v1/notifications/{notif_a.id}/read",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert res_hack.status_code == 403
        assert "belonging to another user" in res_hack.json()["detail"]


@pytest.mark.anyio
async def test_notification_api_preferences_and_filtering(db_session: AsyncSession):
    """Verify notification preferences API and channel opt-out behavior."""
    user, token = await _create_user(db_session, "security_analyst", "analyst")
    app = create_app()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Fetch default preferences
        res_prefs = await client.get(
            "/api/v1/notifications/preferences",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_prefs.status_code == 200
        data_p = res_prefs.json()
        assert data_p["approvals_enabled"] is True
        assert data_p["security_enabled"] is True

        # 2. Update preferences: disable approvals, keep security enabled
        res_update = await client.put(
            "/api/v1/notifications/preferences",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "approvals_enabled": False,
                "documents_enabled": True,
                "analytics_enabled": True,
                "system_enabled": True,
            },
        )
        assert res_update.status_code == 200
        assert res_update.json()["approvals_enabled"] is False

        # 3. Trigger approval notification -> Should be suppressed by preference
        svc = NotificationService(db_session)
        suppressed = await svc.notify_user(
            recipient_user_id=user.id,
            event_type="approval_required",
            title="Suppressed Alert",
            message="You opted out of this.",
        )
        assert suppressed is None

        # 4. Trigger security notification -> MANDATORY, cannot be suppressed
        mandatory = await svc.notify_user(
            recipient_user_id=user.id,
            event_type="security_alert",
            title="Critical Breach Alert",
            message="Policy enforced security notification.",
        )
        assert mandatory is not None
        await db_session.commit()

        # 5. Check unread count API
        res_cnt = await client.get(
            "/api/v1/notifications/unread-count",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_cnt.status_code == 200
        assert res_cnt.json()["unread_count"] == 1
