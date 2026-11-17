"""
Unit Tests — Consecutive Requests, Sequential State Isolation & Concurrency.

Verifies:
1. First and second sequential requests execute reliably without state leakage.
2. Repeated identical requests produce consistent policy evaluations.
3. Different consecutive questions maintain clear boundaries.
4. Recovery after an error (e.g. policy denial) allows subsequent valid requests.
5. Requests from separate authenticated users maintain strict identity and clearance isolation.
6. Concurrent requests execute without race conditions or database deadlocks.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.ai.schemas import DataSensitivity
from src.auth.permissions import SystemRole
from src.auth.rbac import AuthContext
from src.core.exceptions import PolicyDeniedError
from src.orchestrator.engine import OrchestratorEngine


def _make_auth(user_id: str, role: SystemRole, permissions: set[str] | None = None) -> AuthContext:
    from src.auth.permissions import DEFAULT_ROLE_PERMISSIONS

    perms = permissions or {str(p) for p in DEFAULT_ROLE_PERMISSIONS.get(role, set())}
    return AuthContext(user_id=user_id, role=role.value, permissions=perms)


@pytest.mark.asyncio
async def test_consecutive_sequential_requests(db_session: AsyncSession) -> None:
    """Sequential requests must execute without state contamination or session errors."""
    engine = OrchestratorEngine(db_session)
    admin_auth = _make_auth("user-seq-1", SystemRole.ADMIN)

    # 1. First request
    res1 = await engine.execute(
        auth=admin_auth,
        user_input="First query: What are ServerGen AI core capabilities?",
        data_sensitivity=DataSensitivity.INTERNAL,
    )
    assert res1.policy_decision == "allow"
    assert res1.request_id

    # 2. Second request (consecutive)
    res2 = await engine.execute(
        auth=admin_auth,
        user_input="Second query: Explain remote work VPN connection standards.",
        data_sensitivity=DataSensitivity.INTERNAL,
    )
    assert res2.policy_decision == "allow"
    assert res2.request_id
    assert res2.request_id != res1.request_id

    # 3. Repeated identical request
    res3 = await engine.execute(
        auth=admin_auth,
        user_input="Second query: Explain remote work VPN connection standards.",
        data_sensitivity=DataSensitivity.INTERNAL,
    )
    assert res3.policy_decision == "allow"
    assert res3.request_id != res2.request_id


@pytest.mark.asyncio
async def test_request_recovery_after_error(db_session: AsyncSession) -> None:
    """An engine failure or policy denial must not corrupt subsequent requests."""
    engine = OrchestratorEngine(db_session)

    # User with no ai.execute permission triggers PolicyDeniedError
    denied_auth = AuthContext(
        user_id="user-no-perm",
        role="general_employee",
        permissions={"document.read"},  # Missing ai.execute
    )
    with pytest.raises(PolicyDeniedError):
        await engine.execute(
            auth=denied_auth,
            user_input="Attempt unauthorized execution",
            data_sensitivity=DataSensitivity.PUBLIC,
        )

    # Subsequent valid request from an authorized user succeeds cleanly
    admin_auth = _make_auth("admin-recovered", SystemRole.ADMIN)
    res_valid = await engine.execute(
        auth=admin_auth,
        user_input="Summarize general system architecture overview.",
        data_sensitivity=DataSensitivity.PUBLIC,
    )
    assert res_valid.policy_decision == "allow"
    assert res_valid.success is True or res_valid.content != ""


@pytest.mark.asyncio
async def test_separate_users_clearance_isolation(db_session: AsyncSession) -> None:
    """
    Consecutive requests from different users must not leak clearance or documents.
    Operator with CONFIDENTIAL clearance executes runbook query (ALLOW).
    Employee with INTERNAL clearance querying right after has CONFIDENTIAL withheld.
    """
    engine = OrchestratorEngine(db_session)

    operator_auth = _make_auth("operator-isolated", SystemRole.IT_OPERATOR)
    employee_auth = _make_auth("emp-isolated", SystemRole.GENERAL_EMPLOYEE)

    # IT Operator request (CONFIDENTIAL clearance allows runbook)
    res_op = await engine.execute(
        auth=operator_auth,
        user_input="What diagnostic checks are performed during server maintenance?",
        data_sensitivity=DataSensitivity.INTERNAL,
    )
    assert res_op.policy_decision == "allow"

    # Employee request immediately following
    res_emp = await engine.execute(
        auth=employee_auth,
        user_input="What diagnostic checks are performed during server maintenance?",
        data_sensitivity=DataSensitivity.INTERNAL,
    )
    assert res_emp.policy_decision == "allow"

    # Ensure employee did NOT receive unauthorized confidential records
    withheld_warnings = [
        w
        for w in res_emp.warnings
        if isinstance(w, str) and w.startswith("rag_unauthorized_records_withheld")
    ]
    assert len(withheld_warnings) > 0 or not any(
        "IT Operations & Server Diagnostic Runbook" in str(src) for src in res_emp.grounded_sources
    )


@pytest.mark.asyncio
async def test_concurrent_requests_handling() -> None:
    """Multiple simultaneous requests execute concurrently across independent DB sessions."""
    from tests.conftest import TestingSessionLocal

    admin_auth = _make_auth("admin-concurrent", SystemRole.ADMIN)

    async def _make_call(idx: int):
        async with TestingSessionLocal() as session:
            engine = OrchestratorEngine(session)
            res = await engine.execute(
                auth=admin_auth,
                user_input=f"Concurrent probe #{idx}: What is ServerGen AI architecture?",
                data_sensitivity=DataSensitivity.PUBLIC,
            )
            await session.commit()
            return res

    results = await asyncio.gather(
        _make_call(1),
        _make_call(2),
        _make_call(3),
    )

    assert len(results) == 3
    for r in results:
        assert r.policy_decision == "allow"
        assert r.request_id
    # All request IDs must be distinct
    req_ids = {r.request_id for r in results}
    assert len(req_ids) == 3
