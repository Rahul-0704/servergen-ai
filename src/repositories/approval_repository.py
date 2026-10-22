"""
ServerGen AI — Approval Repository.

All state transitions are single conditional UPDATEs (compare-and-set), so two
concurrent reviewers — or an approver racing with a cancel — can never both
"win": the loser sees rowcount 0.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.approval import ApprovalRequest


class ApprovalRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, approval: ApprovalRequest) -> ApprovalRequest:
        self.db.add(approval)
        await self.db.flush()
        return approval

    async def get_by_id(self, approval_id: uuid.UUID) -> ApprovalRequest | None:
        stmt = select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_pending(self) -> list[ApprovalRequest]:
        stmt = select(ApprovalRequest).where(ApprovalRequest.status == "pending")
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_filtered(
        self,
        *,
        requester_id: uuid.UUID | None = None,
        exclude_requester_id: uuid.UUID | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[ApprovalRequest], int]:
        """List approvals (newest first) with optional scoping, plus the total count."""
        conditions = []
        if requester_id is not None:
            conditions.append(ApprovalRequest.requester_user_id == requester_id)
        if exclude_requester_id is not None:
            conditions.append(ApprovalRequest.requester_user_id != exclude_requester_id)
        if status:
            conditions.append(ApprovalRequest.status == status)

        total = (
            await self.db.execute(
                select(func.count()).select_from(ApprovalRequest).where(*conditions)
            )
        ).scalar_one()
        stmt = (
            select(ApprovalRequest)
            .where(*conditions)
            .order_by(ApprovalRequest.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all()), int(total)

    async def resolve(
        self,
        approval_id: uuid.UUID,
        status: str,
        reviewer_user_id: uuid.UUID | None = None,
        notes: str = "",
    ) -> ApprovalRequest | None:
        """
        Move a PENDING approval to ``status`` atomically.

        Returns the updated row, or None if it was no longer pending (lost a race).
        """
        values: dict = {"status": status, "resolved_at": datetime.now(UTC)}
        if reviewer_user_id:
            values["reviewer_user_id"] = reviewer_user_id
        if notes:
            values["reviewer_notes"] = notes
        stmt = (
            update(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id, ApprovalRequest.status == "pending")
            .values(**values)
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        if (result.rowcount or 0) != 1:
            return None
        approval = await self.get_by_id(approval_id)
        if approval is not None:
            await self.db.refresh(approval)
        return approval

    async def consume(self, approval_id: uuid.UUID) -> bool:
        """
        Mark an APPROVED approval as used. True only for the single caller that wins.

        This is what makes an approval single-use: it runs BEFORE the operation does.
        """
        stmt = (
            update(ApprovalRequest)
            .where(
                ApprovalRequest.id == approval_id,
                ApprovalRequest.status == "approved",
                ApprovalRequest.consumed_at.is_(None),
            )
            .values(consumed_at=datetime.now(UTC))
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return (result.rowcount or 0) == 1

    async def expire_pending(self, now: datetime) -> list[ApprovalRequest]:
        """Mark expired PENDING approvals as EXPIRED; return the rows that changed."""
        ids = list(
            (
                await self.db.execute(
                    select(ApprovalRequest.id).where(
                        ApprovalRequest.status == "pending", ApprovalRequest.expires_at < now
                    )
                )
            )
            .scalars()
            .all()
        )
        expired: list[ApprovalRequest] = []
        for approval_id in ids:
            updated = await self.resolve(approval_id, status="expired")
            if updated is not None:
                expired.append(updated)
        return expired
