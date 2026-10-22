"""
Integration Test — PostgreSQL Tamper-Evident Audit Ledger.

Verifies:
 1. Advisory-lock serialization (pg_advisory_xact_lock) on real PostgreSQL.
 2. Sequential SHA-256 hash-chain creation.
 3. Continuous hash chain verification.
 4. Tamper detection: modifying a record in PostgreSQL causes verification failure.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.audit_service import AuditEventType, AuditService, VerificationResult


@pytest.mark.asyncio
async def test_postgres_advisory_lock_and_chain(pg_session: AsyncSession) -> None:
    """AuditService records events with advisory locks and forms a valid chain on PostgreSQL."""
    await pg_session.execute(text("TRUNCATE TABLE audit_events;"))
    await pg_session.commit()

    audit = AuditService(pg_session)
    user_id = str(uuid.uuid4())

    e1 = await audit.record(
        event_type=AuditEventType.LOGIN_SUCCESS,
        action="login",
        request_id="req-int-1",
        user_id=user_id,
        role="administrator",
        resource="/auth/login",
    )
    e2 = await audit.record(
        event_type=AuditEventType.LLM_REQUEST,
        action="llm_request",
        request_id="req-int-2",
        user_id=user_id,
        role="administrator",
        resource="llm",
        model="gemma3:4b",
    )
    e3 = await audit.record(
        event_type=AuditEventType.EXECUTION_COMPLETED,
        action="execution_completed",
        request_id="req-int-3",
        user_id=user_id,
        role="administrator",
        resource="llm",
    )

    await pg_session.commit()

    assert e1.sequence_number < e2.sequence_number < e3.sequence_number
    assert e2.previous_hash == e1.event_hash
    assert e3.previous_hash == e2.event_hash

    # Verify chain
    verification = await audit.verify_integrity()
    assert verification.status == VerificationResult.VERIFIED
    assert verification.events_checked >= 3
    assert verification.broken_at_sequence is None


@pytest.mark.asyncio
async def test_postgres_tamper_detection(pg_session: AsyncSession) -> None:
    """Tampering with an audit row in PostgreSQL is detected by verify_chain()."""
    await pg_session.execute(text("TRUNCATE TABLE audit_events;"))
    await pg_session.commit()

    audit = AuditService(pg_session)
    user_id = str(uuid.uuid4())

    await audit.record(
        event_type=AuditEventType.LOGIN_SUCCESS,
        action="login_tamper_test",
        request_id="req-tamper-1",
        user_id=user_id,
        role="administrator",
    )
    e_target = await audit.record(
        event_type=AuditEventType.LLM_REQUEST,
        action="llm_tamper_test",
        request_id="req-tamper-2",
        user_id=user_id,
        role="administrator",
    )
    await audit.record(
        event_type=AuditEventType.EXECUTION_COMPLETED,
        action="complete_tamper_test",
        request_id="req-tamper-3",
        user_id=user_id,
        role="administrator",
    )
    await pg_session.commit()

    # Tamper with the row directly in PostgreSQL
    await pg_session.execute(
        text("UPDATE audit_events SET action = 'tampered_action' WHERE id = :id"),
        {"id": e_target.id},
    )
    await pg_session.commit()

    # Expire cached session objects
    pg_session.expire_all()

    # Integrity verification must fail
    verification = await audit.verify_integrity()
    assert verification.status == VerificationResult.BROKEN
    assert verification.broken_at_sequence == e_target.sequence_number
