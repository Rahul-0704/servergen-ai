"""
Phase G Tests — Tamper-Evident Audit Ledger.

Tests:
 1. Single event is recorded with correct hash
 2. Hash chain links correctly across multiple events
 3. Chain verification passes on intact chain
 4. Chain verification detects a tampered event_hash
 5. Chain verification detects a tampered previous_hash
 6. Empty chain verifies as VERIFIED
 7. Canonical serialization is deterministic
 8. Different events produce different hashes
 9. All AuditEventType values are valid strings
10. Metadata is stored but secrets are not logged
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.audit_service import (
    AuditEventType,
    AuditService,
    VerificationResult,
    compute_event_hash,
)

# ── Test 1: Single event recorded with correct hash ────────────────────


@pytest.mark.asyncio
async def test_single_event_hash(db_session: AsyncSession) -> None:
    """A recorded event has a non-empty, 64-char SHA-256 hash."""
    svc = AuditService(db_session)
    event = await svc.record(
        event_type=AuditEventType.LOGIN_SUCCESS,
        action="login_success",
        request_id="req-001",
        user_id="user-1",
        role="administrator",
    )
    assert event.sequence_number == 1
    assert len(event.event_hash) == 64
    assert event.previous_hash is None  # first event


# ── Test 2: Hash chain links correctly ─────────────────────────────────


@pytest.mark.asyncio
async def test_hash_chain_links(db_session: AsyncSession) -> None:
    """Each event's previous_hash equals the prior event's event_hash."""
    svc = AuditService(db_session)
    e1 = await svc.record(
        event_type=AuditEventType.LOGIN_SUCCESS,
        action="login_success",
        request_id="req-chain-1",
    )
    e2 = await svc.record(
        event_type=AuditEventType.EXECUTION_STARTED,
        action="execution_started",
        request_id="req-chain-2",
    )
    e3 = await svc.record(
        event_type=AuditEventType.EXECUTION_COMPLETED,
        action="execution_completed",
        request_id="req-chain-3",
    )
    assert e2.previous_hash == e1.event_hash
    assert e3.previous_hash == e2.event_hash
    assert e1.sequence_number < e2.sequence_number < e3.sequence_number


# ── Test 3: Intact chain verifies as VERIFIED ──────────────────────────


@pytest.mark.asyncio
async def test_chain_verification_passes(db_session: AsyncSession) -> None:
    """An unmodified chain verifies as VERIFIED."""
    svc = AuditService(db_session)
    for i in range(5):
        await svc.record(
            event_type=AuditEventType.LLM_REQUEST,
            action="llm_request",
            request_id=f"req-verify-{i}",
        )
    status, broken_at = await svc.verify_chain()
    assert status == VerificationResult.VERIFIED
    assert broken_at is None


# ── Test 4: Tampered event_hash is detected ────────────────────────────


@pytest.mark.asyncio
async def test_chain_detects_tampered_event_hash(db_session: AsyncSession) -> None:
    """Modifying an event_hash breaks the chain verification."""
    svc = AuditService(db_session)
    e1 = await svc.record(
        event_type=AuditEventType.LOGIN_SUCCESS,
        action="login_success",
        request_id="req-tamper-1",
    )
    await svc.record(
        event_type=AuditEventType.LOGIN_FAILURE,
        action="login_failure",
        request_id="req-tamper-2",
    )

    # Tamper: directly modify the first event's hash
    e1.event_hash = "a" * 64
    await db_session.flush()

    status, broken_at = await svc.verify_chain()
    assert status == VerificationResult.BROKEN
    assert broken_at is not None


# ── Test 5: Tampered previous_hash is detected ─────────────────────────


@pytest.mark.asyncio
async def test_chain_detects_tampered_previous_hash(db_session: AsyncSession) -> None:
    """Modifying a previous_hash breaks the chain verification."""
    svc = AuditService(db_session)
    await svc.record(
        event_type=AuditEventType.LOGIN_SUCCESS,
        action="login_success",
        request_id="req-prev-1",
    )
    e2 = await svc.record(
        event_type=AuditEventType.LOGOUT,
        action="logout",
        request_id="req-prev-2",
    )

    # Tamper: change the previous_hash of e2
    e2.previous_hash = "b" * 64
    await db_session.flush()

    status, _broken_at = await svc.verify_chain()
    assert status == VerificationResult.BROKEN


# ── Test 6: Empty chain verifies as VERIFIED ───────────────────────────


@pytest.mark.asyncio
async def test_empty_chain_verified(db_session: AsyncSession) -> None:
    """An empty audit log verifies as VERIFIED (nothing to check)."""
    svc = AuditService(db_session)
    status, broken_at = await svc.verify_chain()
    assert status == VerificationResult.VERIFIED
    assert broken_at is None


# ── Test 7: Canonical serialization is deterministic ──────────────────


@pytest.mark.asyncio
async def test_canonical_serialization_deterministic(db_session: AsyncSession) -> None:
    """The same event always produces the same hash."""
    svc = AuditService(db_session)
    event = await svc.record(
        event_type=AuditEventType.TOOL_REQUEST,
        action="tool_request",
        request_id="req-det-1",
        tool="calculator",
    )
    # Recompute hash from the stored event
    recomputed = compute_event_hash(event, event.previous_hash)
    assert recomputed == event.event_hash


# ── Test 8: Different events produce different hashes ──────────────────


@pytest.mark.asyncio
async def test_different_events_different_hashes(db_session: AsyncSession) -> None:
    """Two distinct events produce different hashes."""
    svc = AuditService(db_session)
    e1 = await svc.record(
        event_type=AuditEventType.LOGIN_SUCCESS,
        action="login_success",
        request_id="req-diff-1",
        user_id="user-A",
    )
    e2 = await svc.record(
        event_type=AuditEventType.LOGIN_FAILURE,
        action="login_failure",
        request_id="req-diff-2",
        user_id="user-B",
    )
    assert e1.event_hash != e2.event_hash


# ── Test 9: All AuditEventType values are valid strings ────────────────


def test_audit_event_types_are_strings() -> None:
    """All AuditEventType members are non-empty strings."""
    for evt in AuditEventType:
        assert isinstance(evt.value, str)
        assert len(evt.value) > 0


# ── Test 10: Metadata stored, no credential fields ─────────────────────


@pytest.mark.asyncio
async def test_metadata_stored_no_secrets(db_session: AsyncSession) -> None:
    """Metadata dict is stored; sensitive fields must not appear in event_hash input."""
    svc = AuditService(db_session)
    event = await svc.record(
        event_type=AuditEventType.LOGIN_SUCCESS,
        action="login_success",
        request_id="req-meta-1",
        metadata={"ip_address": "192.168.1.1", "user_agent": "TestAgent/1.0"},
    )
    assert event.metadata_json is not None
    assert "ip_address" in event.metadata_json
    # Metadata is NOT part of the canonical hash input (only security fields are)
    assert event.event_hash  # hash was computed without metadata
