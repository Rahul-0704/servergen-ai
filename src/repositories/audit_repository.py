"""
ServerGen AI — Audit Repository.

Persistence for the Tamper-Evident AI Activity Ledger. Appends are serialised
with a PostgreSQL transaction-scoped advisory lock so concurrent requests can
never allocate the same sequence number or fork the hash chain.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit import AuditEvent

# Arbitrary application-wide constant identifying the audit-chain advisory lock.
_AUDIT_CHAIN_LOCK_KEY = 7_266_891_001


@dataclass(frozen=True)
class AuditFilters:
    """Optional filters for listing audit events."""

    event_type: str | None = None
    action: str | None = None
    user_id: str | None = None
    request_id: str | None = None
    decision: str | None = None
    risk_level: str | None = None
    since: datetime | None = None
    until: datetime | None = None


class AuditRepository:
    """Data access for audit events."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def lock_chain(self) -> None:
        """
        Serialise chain appends for the rest of the current transaction.

        PostgreSQL: ``pg_advisory_xact_lock`` (released on commit/rollback).
        Other dialects (SQLite, dev/unit tests only) already serialise writers.
        """
        if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
            await self.db.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": _AUDIT_CHAIN_LOCK_KEY}
            )

    async def get_tail(self) -> tuple[int, str] | None:
        """Return (sequence_number, event_hash) of the newest event, or None if empty."""
        stmt = (
            select(AuditEvent.sequence_number, AuditEvent.event_hash)
            .order_by(AuditEvent.sequence_number.desc())
            .limit(1)
        )
        row = (await self.db.execute(stmt)).first()
        return (row[0], row[1]) if row else None

    async def get_next_sequence(self) -> int:
        """Next sequence number (max + 1, or 1 if empty)."""
        tail = await self.get_tail()
        return (tail[0] + 1) if tail else 1

    async def get_last_hash(self) -> str | None:
        """event_hash of the most recent event (for chain linking)."""
        tail = await self.get_tail()
        return tail[1] if tail else None

    async def create(self, event: AuditEvent) -> AuditEvent:
        """Insert an event."""
        self.db.add(event)
        await self.db.flush()
        return event

    @staticmethod
    def _apply_filters(stmt: Select, f: AuditFilters) -> Select:
        if f.event_type:
            stmt = stmt.where(AuditEvent.event_type == f.event_type)
        if f.action:
            stmt = stmt.where(AuditEvent.action == f.action)
        if f.user_id:
            stmt = stmt.where(AuditEvent.user_id == f.user_id)
        if f.request_id:
            stmt = stmt.where(AuditEvent.request_id == f.request_id)
        if f.decision:
            stmt = stmt.where(AuditEvent.decision == f.decision)
        if f.risk_level:
            stmt = stmt.where(AuditEvent.risk_level == f.risk_level)
        if f.since:
            stmt = stmt.where(AuditEvent.timestamp >= f.since)
        if f.until:
            stmt = stmt.where(AuditEvent.timestamp <= f.until)
        return stmt

    async def list_events(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: AuditFilters | None = None,
        descending: bool = False,
    ) -> list[AuditEvent]:
        """List events ordered by sequence number."""
        order = AuditEvent.sequence_number.desc() if descending else AuditEvent.sequence_number
        stmt = self._apply_filters(select(AuditEvent), filters or AuditFilters())
        stmt = stmt.order_by(order).offset(skip).limit(limit)
        return list((await self.db.execute(stmt)).scalars().all())

    async def count_events(self, filters: AuditFilters | None = None) -> int:
        """Count events matching the filters."""
        stmt = self._apply_filters(
            select(func.count()).select_from(AuditEvent), filters or AuditFilters()
        )
        return int((await self.db.execute(stmt)).scalar_one())

    async def get_by_id(self, event_id: uuid.UUID) -> AuditEvent | None:
        """Get one event by its id."""
        stmt = select(AuditEvent).where(AuditEvent.id == event_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_by_sequence(self, seq: int) -> AuditEvent | None:
        """Get one event by sequence number."""
        stmt = select(AuditEvent).where(AuditEvent.sequence_number == seq)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def iter_chain(self, batch_size: int = 1000) -> AsyncIterator[list[AuditEvent]]:
        """Yield the whole chain in sequence order using keyset pagination."""
        last_seq = 0
        while True:
            stmt = (
                select(AuditEvent)
                .where(AuditEvent.sequence_number > last_seq)
                .order_by(AuditEvent.sequence_number)
                .limit(batch_size)
            )
            batch = list((await self.db.execute(stmt)).scalars().all())
            if not batch:
                return
            yield batch
            last_seq = batch[-1].sequence_number
