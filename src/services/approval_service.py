"""
ServerGen AI — Approval Service.

Manages the lifecycle of approval requests for HIGH/CRITICAL operations.

CRITICAL SECURITY RULES
- A PENDING approval never lets anything execute.
- An APPROVED operation is only executed after: status check, expiry check,
  single-use claim, and operation-fingerprint verification (+ a fresh policy pass).
- Requester != approver (separation of duties) for every approval.
- CRITICAL-risk operations can only be approved by an administrator.
- An approval id can never authorise a different operation (fingerprint binding).
- Every transition is written to the tamper-evident audit ledger.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.schemas import OperationContext, RiskAssessment
from src.auth.permissions import PermissionCode, SystemRole
from src.core.config import get_settings
from src.core.exceptions import ApprovalError, AuthorizationError, NotFoundError
from src.models.approval import ApprovalRequest
from src.repositories.approval_repository import ApprovalRepository
from src.services.audit_service import AuditEventType, AuditService

if TYPE_CHECKING:
    from src.auth.rbac import AuthContext


class ApprovalStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


def compute_operation_fingerprint(context: OperationContext, risk: RiskAssessment) -> str:
    """
    Deterministic SHA-256 over the security-relevant attributes of an operation.

    The fingerprint binds an approval to exactly one operation; any change to it
    (user, role, resource, tool, parameters, sensitivity, category, risk ...)
    produces a different hash and invalidates the approval.
    """
    canonical = {
        "user_id": context.user_id,
        "role": context.role,
        "permission": context.permission,
        "resource": context.resource,
        "action": context.action,
        "agent": context.agent,
        "tool": context.tool,
        "data_sensitivity": context.data_sensitivity,
        "task_category": context.task_category,
        "operation_type": context.operation_type,
        "production_affecting": context.production_affecting,
        "potential_impact": context.potential_impact,
        "risk_level": risk.risk_level,
        "parameters": context.parameters,
    }
    serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


def to_uuid(value: str) -> uuid.UUID:
    """Parse a UUID string; non-UUID identifiers (tests only) map deterministically via uuid5."""
    try:
        return uuid.UUID(value)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_DNS, value)


def _aware(value: datetime) -> datetime:
    """Treat naive datetimes (SQLite) as UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class ApprovalService:
    """Approval lifecycle with security enforcement and audit."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = ApprovalRepository(db)
        self.audit = AuditService(db)

    # ── Creation & reads ─────────────────────────────────────────────

    async def create(
        self,
        request_id: str,
        context: OperationContext,
        risk: RiskAssessment,
        operation_summary: str,
        payload: dict | None = None,
    ) -> ApprovalRequest:
        """Create a PENDING approval. The operation stays BLOCKED until it is approved."""
        now = datetime.now(UTC)
        approval = ApprovalRequest(
            id=uuid.uuid4(),
            request_id=request_id,
            requester_user_id=to_uuid(context.user_id),
            requester_role=context.role,
            operation_summary=operation_summary[:1000],
            task_classification_json={
                "category": str(context.task_category),
                "operation_type": str(context.operation_type),
            },
            risk_assessment_json={
                "risk_level": str(risk.risk_level),
                "factors": risk.factors,
                "requires_approval": risk.requires_approval,
            },
            operation_payload=payload,
            operation_fingerprint=compute_operation_fingerprint(context, risk),
            status=ApprovalStatus.PENDING,
            created_at=now,
            expires_at=now + timedelta(hours=get_settings().APPROVAL_TTL_HOURS),
        )
        created = await self.repo.create(approval)
        await self._audit(
            AuditEventType.APPROVAL_CREATED,
            created,
            actor_id=context.user_id,
            actor_role=context.role,
            decision="require_approval",
        )
        return created

    async def get(self, approval_id: uuid.UUID) -> ApprovalRequest:
        """Get an approval (lazily expiring it if its TTL has passed)."""
        approval = await self.repo.get_by_id(approval_id)
        if approval is None:
            raise NotFoundError(f"Approval {approval_id} not found")
        return await self._expire_if_due(approval)

    async def get_visible(self, approval_id: uuid.UUID, auth: AuthContext) -> ApprovalRequest:
        """
        Get an approval the caller is allowed to see: their own, or any if they can review.

        A foreign approval reports "not found" (not "forbidden") so ids cannot be probed.
        """
        approval = await self.get(approval_id)
        if approval.requester_user_id == to_uuid(auth.user_id) or auth.has_permission(
            PermissionCode.APPROVAL_APPROVE
        ):
            return approval
        raise NotFoundError(f"Approval {approval_id} not found")

    async def list_for(
        self,
        auth: AuthContext,
        scope: str = "mine",
        status: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[ApprovalRequest], int]:
        """
        List approvals. ``mine`` = requested by the caller; ``review`` = other users'
        requests awaiting a decision (requires approval.approve).
        """
        await self.expire_stale()
        me = to_uuid(auth.user_id)
        if scope == "review":
            if not auth.has_permission(PermissionCode.APPROVAL_APPROVE):
                raise AuthorizationError("Permission 'approval.approve' required")
            return await self.repo.list_filtered(
                exclude_requester_id=me, status=status, skip=skip, limit=limit
            )
        return await self.repo.list_filtered(requester_id=me, status=status, skip=skip, limit=limit)

    # ── Decisions ────────────────────────────────────────────────────

    async def approve(
        self,
        approval_id: uuid.UUID,
        reviewer_user_id: str,
        reviewer_role: str,
        notes: str = "",
    ) -> ApprovalRequest:
        """
        Approve a pending request.

        Enforces: PENDING + not expired, reviewer != requester, and administrator-only
        approval of CRITICAL-risk operations. (approval.approve is checked at the API.)
        """
        approval = await self.get(approval_id)
        self._assert_pending(approval)
        self._assert_not_expired(approval)
        self._assert_separation_of_duties(approval, reviewer_user_id)
        self._assert_approval_level(approval, reviewer_role)

        resolved = await self.repo.resolve(
            approval_id,
            status=ApprovalStatus.APPROVED,
            reviewer_user_id=to_uuid(reviewer_user_id),
            notes=notes,
        )
        if resolved is None:
            raise ApprovalError("Approval was changed concurrently — no longer pending")
        await self._audit(
            AuditEventType.APPROVAL_APPROVED,
            resolved,
            actor_id=reviewer_user_id,
            actor_role=reviewer_role,
        )
        return resolved

    async def reject(
        self,
        approval_id: uuid.UUID,
        reviewer_user_id: str,
        notes: str = "",
        reviewer_role: str = "",
    ) -> ApprovalRequest:
        """Reject a pending approval (separation of duties applies)."""
        approval = await self.get(approval_id)
        self._assert_pending(approval)
        self._assert_separation_of_duties(approval, reviewer_user_id)
        resolved = await self.repo.resolve(
            approval_id,
            status=ApprovalStatus.REJECTED,
            reviewer_user_id=to_uuid(reviewer_user_id),
            notes=notes,
        )
        if resolved is None:
            raise ApprovalError("Approval was changed concurrently — no longer pending")
        await self._audit(
            AuditEventType.APPROVAL_REJECTED,
            resolved,
            actor_id=reviewer_user_id,
            actor_role=reviewer_role,
            decision="deny",
        )
        return resolved

    async def cancel(
        self, approval_id: uuid.UUID, requester_user_id: str, requester_role: str = ""
    ) -> ApprovalRequest:
        """Cancel a pending approval (original requester only)."""
        approval = await self.get(approval_id)
        self._assert_pending(approval)
        if approval.requester_user_id != to_uuid(requester_user_id):
            raise AuthorizationError("Only the requester can cancel their approval")
        resolved = await self.repo.resolve(approval_id, status=ApprovalStatus.CANCELLED)
        if resolved is None:
            raise ApprovalError("Approval was changed concurrently — no longer pending")
        await self._audit(
            AuditEventType.APPROVAL_CANCELLED,
            resolved,
            actor_id=requester_user_id,
            actor_role=requester_role,
        )
        return resolved

    async def expire_stale(self) -> int:
        """Expire all PENDING approvals past their TTL (audited). Returns the count."""
        expired = await self.repo.expire_pending(datetime.now(UTC))
        for approval in expired:
            await self._audit(AuditEventType.APPROVAL_EXPIRED, approval, decision="deny")
        return len(expired)

    # ── Execution gate ───────────────────────────────────────────────

    def verify_fingerprint(
        self, approval: ApprovalRequest, context: OperationContext, risk: RiskAssessment
    ) -> bool:
        """True iff the operation being executed is exactly the one that was approved."""
        return compute_operation_fingerprint(context, risk) == approval.operation_fingerprint

    def assert_executable(
        self, approval: ApprovalRequest, context: OperationContext, risk: RiskAssessment
    ) -> None:
        """
        Raise ApprovalError unless the approved operation may run NOW.

        Checks: APPROVED, not expired, not already consumed, fingerprint matches.
        """
        if approval.status != ApprovalStatus.APPROVED:
            raise ApprovalError(f"Cannot execute: approval status is '{approval.status}'")
        self._assert_not_expired(approval)
        if approval.consumed_at is not None:
            raise ApprovalError("Cannot execute: approval has already been used")
        if not self.verify_fingerprint(approval, context, risk):
            raise ApprovalError(
                "Operation fingerprint mismatch — approval is invalid for this operation"
            )

    async def consume(self, approval: ApprovalRequest) -> None:
        """Claim the approval for execution (single use). Raises if someone else already did."""
        if not await self.repo.consume(approval.id):
            raise ApprovalError("Cannot execute: approval has already been used")
        await self.repo.db.refresh(approval)

    # ── Internal guards ──────────────────────────────────────────────

    async def _expire_if_due(self, approval: ApprovalRequest) -> ApprovalRequest:
        if approval.status == ApprovalStatus.PENDING and _aware(approval.expires_at) < datetime.now(
            UTC
        ):
            resolved = await self.repo.resolve(approval.id, status=ApprovalStatus.EXPIRED)
            if resolved is not None:
                await self._audit(AuditEventType.APPROVAL_EXPIRED, resolved, decision="deny")
                return resolved
        return approval

    @staticmethod
    def _assert_pending(approval: ApprovalRequest) -> None:
        if approval.status != ApprovalStatus.PENDING:
            raise ApprovalError(f"Approval is not pending (status={approval.status!r})")

    @staticmethod
    def _assert_not_expired(approval: ApprovalRequest) -> None:
        if _aware(approval.expires_at) < datetime.now(UTC):
            raise ApprovalError("Approval has expired")

    @staticmethod
    def _assert_separation_of_duties(approval: ApprovalRequest, reviewer_user_id: str) -> None:
        if approval.requester_user_id == to_uuid(reviewer_user_id):
            raise AuthorizationError(
                "Separation of duties violation: requester cannot approve their own request"
            )

    @staticmethod
    def _assert_approval_level(approval: ApprovalRequest, reviewer_role: str) -> None:
        risk_level = (approval.risk_assessment_json or {}).get("risk_level")
        if risk_level == "critical" and reviewer_role != SystemRole.ADMIN.value:
            raise AuthorizationError(
                "CRITICAL-risk operations can only be approved by an administrator"
            )

    async def _audit(
        self,
        event_type: AuditEventType,
        approval: ApprovalRequest,
        *,
        actor_id: str | None = None,
        actor_role: str | None = None,
        decision: str = "allow",
    ) -> None:
        await self.audit.record(
            event_type=event_type,
            action=str(event_type),
            request_id=approval.request_id,
            decision=decision,
            risk_level=(approval.risk_assessment_json or {}).get("risk_level", "low"),
            user_id=actor_id,
            role=actor_role or None,
            resource=f"approval:{approval.id}",
            metadata={
                "approval_id": str(approval.id),
                "requester_user_id": str(approval.requester_user_id),
                "operation_fingerprint": approval.operation_fingerprint,
            },
        )
