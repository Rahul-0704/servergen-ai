"""
ServerGen AI — Refresh Session Repository.

Data access for RefreshSession model. Tokens are stored as SHA-256 hashes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.session import RefreshSession


class SessionRepository:
    """Repository for RefreshSession data access operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, session: RefreshSession) -> RefreshSession:
        """Insert a new refresh session."""
        self.db.add(session)
        await self.db.flush()
        return session

    async def get_by_token_hash(self, token_hash: str) -> RefreshSession | None:
        """Find a refresh session by its token hash."""
        stmt = select(RefreshSession).where(RefreshSession.refresh_token_hash == token_hash)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke(self, session_id: uuid.UUID, replaced_by: uuid.UUID | None = None) -> None:
        """Revoke a specific refresh session."""
        stmt = (
            update(RefreshSession)
            .where(RefreshSession.id == session_id)
            .values(
                revoked=True,
                revoked_at=datetime.now(UTC),
                replaced_by=replaced_by,
            )
        )
        await self.db.execute(stmt)

    async def revoke_family(self, family_id: str) -> None:
        """Revoke all sessions in a token family (reuse detection)."""
        stmt = (
            update(RefreshSession)
            .where(RefreshSession.family_id == family_id, RefreshSession.revoked.is_(False))
            .values(revoked=True, revoked_at=datetime.now(UTC))
        )
        await self.db.execute(stmt)

    async def revoke_all_user_sessions(self, user_id: uuid.UUID) -> None:
        """Revoke all refresh sessions for a user (e.g., on password change)."""
        stmt = (
            update(RefreshSession)
            .where(RefreshSession.user_id == user_id, RefreshSession.revoked.is_(False))
            .values(revoked=True, revoked_at=datetime.now(UTC))
        )
        await self.db.execute(stmt)
