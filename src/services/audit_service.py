"""
ServerGen AI — Tamper-Evident AI Activity Ledger (audit service).

A hash-linked audit mechanism that DETECTS modification of recorded events:

    event_hash(N) = SHA-256( canonical_json(event_N) + event_hash(N-1) )

Every field of the event — including ``metadata`` — is part of the canonical
data. Verification walks the entire chain and reports the first record whose
content, link, or sequence number is inconsistent.

LIMITATIONS (by design, documented in SECURITY.md): this is tamper-EVIDENT, not
tamper-proof. Someone with database write access who recomputes every
subsequent hash can rewrite history, and truncating the newest events is not
detectable without an external anchor of the latest hash.

NEVER store passwords, tokens, API keys or credentials — values under sensitive
metadata keys are redacted before persistence.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit import AuditEvent
from src.repositories.audit_repository import AuditRepository

# Process-wide serialization lock for audit event sequence assignment and chain integrity
_audit_append_lock = asyncio.Lock()



class AuditEventType(StrEnum):
    """Audit event kinds covered by the ledger."""

    # Auth
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    TOKEN_REFRESH = "token_refresh"
    # Authorization
    AUTHORIZATION_DENIED = "authorization_denied"
    POLICY_DENIED = "policy_denied"
    # Approvals
    APPROVAL_CREATED = "approval_created"
    APPROVAL_APPROVED = "approval_approved"
    APPROVAL_REJECTED = "approval_rejected"
    APPROVAL_EXPIRED = "approval_expired"
    APPROVAL_CANCELLED = "approval_cancelled"
    # Execution
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_BLOCKED = "execution_blocked"
    # Tools / LLM
    TOOL_REQUEST = "tool_request"
    TOOL_BLOCKED = "tool_blocked"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    # Administration
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DISABLED = "user_disabled"
    USER_ENABLED = "user_enabled"
    # Document Management & RAG
    DOCUMENT_UPLOAD = "document_upload"
    DOCUMENT_VERSION_CREATED = "document_version_created"
    DOCUMENT_INDEXING_STARTED = "document_indexing_started"
    DOCUMENT_INDEXING_COMPLETED = "document_indexing_completed"
    DOCUMENT_INDEXING_FAILED = "document_indexing_failed"
    DOCUMENT_REINDEX_REQUESTED = "document_reindex_requested"
    DOCUMENT_DELETED = "document_deleted"
    DOCUMENT_PERMISSION_CHANGED = "document_permission_changed"
    DOCUMENT_ACCESS_DENIED = "document_access_denied"
    RAG_QUERY = "rag_query"
    RAG_RETRIEVAL = "rag_retrieval"
    RAG_EVALUATION = "rag_evaluation"
    # System
    SYSTEM_ERROR = "system_error"


class VerificationResult(StrEnum):
    """Outcome of a chain verification."""

    VERIFIED = "verified"
    BROKEN = "broken"


@dataclass(frozen=True)
class IntegrityReport:
    """Detailed result of verifying the ledger."""

    status: VerificationResult
    events_checked: int
    broken_at_sequence: int | None = None
    reason: str = ""


_SENSITIVE_KEY_PARTS = ("password", "token", "secret", "authorization", "api_key", "credential")
_REDACTED = "[REDACTED]"


def redact_metadata(value: Any) -> Any:
    """Return a JSON-safe copy of ``value`` with sensitive keys redacted."""
    if isinstance(value, dict):
        return {
            str(k): (
                _REDACTED
                if any(part in str(k).lower() for part in _SENSITIVE_KEY_PARTS)
                else redact_metadata(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_metadata(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _canonical_event_data(event: AuditEvent) -> str:
    """Deterministic canonical JSON of every hashed field (timestamps at second precision, UTC)."""
    ts = event.timestamp
    ts_str: str | None = None
    if ts is not None:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        ts_str = ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    data = {
        "sequence_number": event.sequence_number,
        "timestamp": ts_str,
        "user_id": event.user_id,
        "role": event.role,
        "request_id": event.request_id,
        "event_type": event.event_type,
        "action": event.action,
        "resource": event.resource,
        "decision": event.decision,
        "risk_level": event.risk_level,
        "agent": event.agent,
        "model": event.model,
        "tool": event.tool,
        "metadata": event.metadata_json,
    }
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def compute_event_hash(event: AuditEvent, previous_hash: str | None) -> str:
    """Compute SHA-256(canonical_event_data + previous_hash)."""
    chain_input = _canonical_event_data(event) + (previous_hash or "")
    return hashlib.sha256(chain_input.encode()).hexdigest()


class AuditService:
    """Append-only (by convention) service for the hash-linked audit ledger."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = AuditRepository(db)

    async def record(
        self,
        event_type: str,
        action: str,
        request_id: str,
        decision: str = "allow",
        risk_level: str = "low",
        user_id: str | None = None,
        role: str | None = None,
        resource: str | None = None,
        agent: str | None = None,
        model: str | None = None,
        tool: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """
        Append an event to the chain.

        The chain lock is taken first, so the tail read, sequence allocation and
        insert are atomic with respect to other writers. The lock is held until
        the surrounding transaction ends — callers that perform slow work (LLM
        calls) after recording should ``commit`` first.
        """
        async with _audit_append_lock:
            await self.repo.lock_chain()
            tail = await self.repo.get_tail()
            seq = (tail[0] + 1) if tail else 1
            previous_hash = tail[1] if tail else None

            event = AuditEvent(
                id=uuid.uuid4(),
                sequence_number=seq,
                timestamp=datetime.now(UTC).replace(microsecond=0),
                user_id=user_id,
                role=role,
                request_id=request_id,
                event_type=str(event_type),
                action=action,
                resource=resource,
                decision=str(decision),
                risk_level=str(risk_level),
                agent=agent or None,
                model=model or None,
                tool=tool or None,
                metadata_json=redact_metadata(metadata) if metadata else None,
                previous_hash=previous_hash,
                event_hash="",
            )
            event.event_hash = compute_event_hash(event, previous_hash)
            return await self.repo.create(event)


    async def verify_integrity(self, batch_size: int = 1000) -> IntegrityReport:
        """
        Walk the ENTIRE chain and verify content, links and sequence continuity.

        Reports the first inconsistent event. Memory use is bounded by ``batch_size``.
        """
        previous_hash: str | None = None
        expected_seq = 1
        checked = 0

        async for batch in self.repo.iter_chain(batch_size):
            for event in batch:
                if event.sequence_number != expected_seq:
                    return IntegrityReport(
                        VerificationResult.BROKEN,
                        checked,
                        event.sequence_number,
                        f"sequence gap: expected {expected_seq}, found {event.sequence_number}",
                    )
                if event.previous_hash != previous_hash:
                    return IntegrityReport(
                        VerificationResult.BROKEN,
                        checked,
                        event.sequence_number,
                        "previous_hash does not match preceding event",
                    )
                if event.event_hash != compute_event_hash(event, previous_hash):
                    return IntegrityReport(
                        VerificationResult.BROKEN,
                        checked,
                        event.sequence_number,
                        "event content does not match its hash",
                    )
                previous_hash = event.event_hash
                expected_seq += 1
                checked += 1

        return IntegrityReport(VerificationResult.VERIFIED, checked)

    async def verify_chain(self, limit: int = 0) -> tuple[VerificationResult, int | None]:
        """Compatibility wrapper: (status, first_broken_sequence). ``limit`` is ignored."""
        report = await self.verify_integrity()
        return report.status, report.broken_at_sequence
