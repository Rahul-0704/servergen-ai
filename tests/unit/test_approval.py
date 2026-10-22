"""
Phase F Tests — Approval Service, Operation Fingerprint, Separation of Duties.

Security tests:
 1. PENDING → MUST NOT EXECUTE (assert_executable raises)
 2. APPROVED → execute only same fingerprint
 3. Modified operation → approval invalid (fingerprint mismatch)
 4. Requester cannot self-approve HIGH/CRITICAL
 5. Expired approval → MUST NOT EXECUTE
 6. Rejected approval → MUST NOT EXECUTE
 7. Cancelled approval → MUST NOT EXECUTE
 8. Fingerprint is deterministic
 9. Different operations produce different fingerprints
10. Approve/reject/cancel lifecycle transitions
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.ai.schemas import DataSensitivity, OperationContext, RiskAssessment, RiskLevel
from src.core.exceptions import ApprovalError, AuthorizationError
from src.models.approval import ApprovalRequest
from src.services.approval_service import (
    ApprovalService,
    ApprovalStatus,
    compute_operation_fingerprint,
)


def _ctx(user_id: str = "user-1") -> OperationContext:
    return OperationContext(
        user_id=user_id,
        role="it_operator",
        permission="system.execute",
        resource="prod-server",
        action="restart",
        tool="system_exec",
        data_sensitivity=DataSensitivity.INTERNAL,
    )


def _risk() -> RiskAssessment:
    return RiskAssessment(
        risk_level=RiskLevel.HIGH,
        factors=["high-risk tool"],
        requires_approval=True,
    )


async def _make_approval(
    db: AsyncSession,
    requester_id: str = "user-1",
    expires_delta: timedelta | None = None,
) -> ApprovalRequest:
    svc = ApprovalService(db)
    ctx = _ctx(user_id=requester_id)
    risk = _risk()
    approval = await svc.create(
        request_id=str(uuid.uuid4()),
        context=ctx,
        risk=risk,
        operation_summary="Restart production server",
    )
    if expires_delta is not None:
        # Manually set expiry for testing
        approval.expires_at = datetime.now(UTC) + expires_delta
        await db.flush()
    return approval


# ── Test 1: PENDING → MUST NOT EXECUTE ─────────────────────────────────


@pytest.mark.asyncio
async def test_pending_must_not_execute(db_session: AsyncSession) -> None:
    """A PENDING approval must block execution."""
    approval = await _make_approval(db_session)
    svc = ApprovalService(db_session)

    assert approval.status == ApprovalStatus.PENDING

    with pytest.raises(ApprovalError, match="pending"):
        svc.assert_executable(approval, _ctx(), _risk())


# ── Test 2: APPROVED → execute only same fingerprint ───────────────────


@pytest.mark.asyncio
async def test_approved_executes_same_fingerprint(db_session: AsyncSession) -> None:
    """APPROVED approval with matching fingerprint allows execution."""
    approval = await _make_approval(db_session, requester_id="user-1")
    svc = ApprovalService(db_session)

    approved = await svc.approve(
        approval.id,
        reviewer_user_id="user-2",
        reviewer_role="manager",
    )
    assert approved.status == ApprovalStatus.APPROVED

    # Same context → same fingerprint → should not raise
    svc.assert_executable(approved, _ctx(user_id="user-1"), _risk())


# ── Test 3: Modified operation → fingerprint mismatch ──────────────────


@pytest.mark.asyncio
async def test_modified_operation_fingerprint_mismatch(db_session: AsyncSession) -> None:
    """Changing the operation after approval invalidates the fingerprint."""
    approval = await _make_approval(db_session, requester_id="user-1")
    svc = ApprovalService(db_session)

    approved = await svc.approve(
        approval.id,
        reviewer_user_id="user-2",
        reviewer_role="manager",
    )

    # Different resource → different fingerprint
    modified_ctx = OperationContext(
        user_id="user-1",
        role="it_operator",
        permission="system.execute",
        resource="different-server",  # changed!
        action="restart",
        tool="system_exec",
        data_sensitivity=DataSensitivity.INTERNAL,
    )

    with pytest.raises(ApprovalError, match="fingerprint"):
        svc.assert_executable(approved, modified_ctx, _risk())


# ── Test 4: Requester cannot self-approve ──────────────────────────────


@pytest.mark.asyncio
async def test_self_approval_denied(db_session: AsyncSession) -> None:
    """Requester cannot approve their own request (separation of duties)."""
    approval = await _make_approval(db_session, requester_id="user-1")
    svc = ApprovalService(db_session)

    with pytest.raises(AuthorizationError, match=r"[Ss]eparation"):
        await svc.approve(
            approval.id,
            reviewer_user_id="user-1",  # same as requester!
            reviewer_role="manager",
        )


# ── Test 5: Expired approval → MUST NOT EXECUTE ────────────────────────


@pytest.mark.asyncio
async def test_expired_approval_blocked(db_session: AsyncSession) -> None:
    """An expired approval cannot be approved or executed."""
    approval = await _make_approval(
        db_session, requester_id="user-1", expires_delta=timedelta(seconds=-1)
    )
    svc = ApprovalService(db_session)

    with pytest.raises(ApprovalError, match=r"[Ee]xpir"):
        await svc.approve(
            approval.id,
            reviewer_user_id="user-2",
            reviewer_role="manager",
        )


# ── Test 6: Rejected approval → MUST NOT EXECUTE ───────────────────────


@pytest.mark.asyncio
async def test_rejected_approval_blocked(db_session: AsyncSession) -> None:
    """A REJECTED approval cannot be executed."""
    approval = await _make_approval(db_session, requester_id="user-1")
    svc = ApprovalService(db_session)

    rejected = await svc.reject(
        approval.id,
        reviewer_user_id="user-2",
        notes="Not authorized",
    )
    assert rejected.status == ApprovalStatus.REJECTED

    with pytest.raises(ApprovalError, match="rejected"):
        svc.assert_executable(rejected, _ctx(), _risk())


# ── Test 7: Cancelled approval → MUST NOT EXECUTE ──────────────────────


@pytest.mark.asyncio
async def test_cancelled_approval_blocked(db_session: AsyncSession) -> None:
    """A CANCELLED approval cannot be executed."""
    approval = await _make_approval(db_session, requester_id="user-1")
    svc = ApprovalService(db_session)

    cancelled = await svc.cancel(approval.id, requester_user_id="user-1")
    assert cancelled.status == ApprovalStatus.CANCELLED

    with pytest.raises(ApprovalError):
        svc.assert_executable(cancelled, _ctx(), _risk())


# ── Test 8: Fingerprint is deterministic ───────────────────────────────


def test_fingerprint_is_deterministic() -> None:
    """Same context + risk always produces the same fingerprint."""
    ctx = _ctx()
    risk = _risk()
    fp1 = compute_operation_fingerprint(ctx, risk)
    fp2 = compute_operation_fingerprint(ctx, risk)
    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 hex


# ── Test 9: Different operations → different fingerprints ──────────────


def test_different_operations_different_fingerprints() -> None:
    """Different operations produce different fingerprints."""
    ctx1 = _ctx(user_id="user-1")
    ctx2 = OperationContext(
        user_id="user-1",
        role="it_operator",
        resource="other-resource",
        action="delete",
        data_sensitivity=DataSensitivity.CONFIDENTIAL,
    )
    risk = _risk()
    assert compute_operation_fingerprint(ctx1, risk) != compute_operation_fingerprint(ctx2, risk)


# ── Test 10: Full lifecycle ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approval_full_lifecycle(db_session: AsyncSession) -> None:
    """Test create → approve → verify full lifecycle."""
    svc = ApprovalService(db_session)
    ctx = _ctx(user_id="user-10")
    risk = _risk()

    # Create
    approval = await svc.create(
        request_id="req-lifecycle",
        context=ctx,
        risk=risk,
        operation_summary="Test lifecycle",
    )
    assert approval.status == ApprovalStatus.PENDING
    assert len(approval.operation_fingerprint) == 64

    # Approve
    approved = await svc.approve(
        approval.id,
        reviewer_user_id="user-99",
        reviewer_role="manager",
        notes="Looks good",
    )
    assert approved.status == ApprovalStatus.APPROVED
    assert approved.reviewer_notes == "Looks good"

    # Verify fingerprint matches
    assert svc.verify_fingerprint(approved, ctx, risk) is True
