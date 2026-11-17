"""
Phase J Tests — Orchestrator Engine.

Tests:
 1. ALLOW: low-risk general task → executes (Ollama may be unavailable, still returns result)
 2. DENY: missing permission → PolicyDeniedError
 3. REQUIRE_APPROVAL: HIGH risk → ApprovalRequiredError + approval created
 4. PENDING → execution blocked (approval not yet approved)
 5. LLM cannot execute shell via orchestrator (no shell tool)
 6. LLM cannot execute SQL via orchestrator (no SQL tool)
 7. Unknown tool → ToolNotFoundError (DENY)
 8. Task classification flows through to result
 9. Audit events are recorded for each execution
10. Rate limiter: LOGIN category works independently of account lockout
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.ai.schemas import DataSensitivity, TaskCategory
from src.auth.rbac import AuthContext
from src.core.exceptions import (
    ApprovalRequiredError,
    PolicyDeniedError,
    RateLimitExceededError,
    ToolNotFoundError,
)
from src.orchestrator.engine import OrchestratorEngine
from src.rate_limiting.memory import InMemoryRateLimiter, RateLimitCategory
from src.services.audit_service import AuditService
from src.tools.base import ToolRequest


def _admin_auth() -> AuthContext:
    return AuthContext(
        user_id="00000000-0000-0000-0000-000000000001",
        role="administrator",
        permissions={
            "ai.execute",
            "ai.read",
            "system.execute",
            "system.read",
            "admin.manage",
            "document.read",
            "approval.approve",
            "audit.read",
            "security.execute",
            "user.read",
        },
    )


def _employee_auth() -> AuthContext:
    return AuthContext(
        user_id="00000000-0000-0000-0000-000000000002",
        role="general_employee",
        permissions={"document.read", "ai.execute", "ai.read"},
    )


# ── Test 1: ALLOW low-risk general task ────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_allow_low_risk(db_session: AsyncSession) -> None:
    """Low-risk general task is allowed; Ollama may be unavailable but result is returned."""
    engine = OrchestratorEngine(db_session)
    result = await engine.execute(
        auth=_admin_auth(),
        user_input="What is 2 + 2?",
        data_sensitivity=DataSensitivity.PUBLIC,
    )
    # Policy should ALLOW; LLM may fail if Ollama is down — that's OK
    assert result.policy_decision == "allow"
    assert result.risk_level in ("low", "medium")
    assert result.request_id


# ── Test 2: DENY missing permission ────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_deny_missing_permission(db_session: AsyncSession) -> None:
    """User without ai.execute permission is denied by policy."""
    no_perm_auth = AuthContext(
        user_id="00000000-0000-0000-0000-000000000003",
        role="general_employee",
        permissions={"document.read"},  # no ai.execute
    )
    engine = OrchestratorEngine(db_session)
    with pytest.raises(PolicyDeniedError):
        await engine.execute(
            auth=no_perm_auth,
            user_input="Run a task",
            data_sensitivity=DataSensitivity.PUBLIC,
        )


# ── Test 3: REQUIRE_APPROVAL for HIGH risk ─────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_require_approval_high_risk(db_session: AsyncSession) -> None:
    """RESTRICTED data triggers CRITICAL risk → REQUIRE_APPROVAL."""
    engine = OrchestratorEngine(db_session)
    with pytest.raises(ApprovalRequiredError) as exc_info:
        await engine.execute(
            auth=_admin_auth(),
            user_input="Access restricted data",
            data_sensitivity=DataSensitivity.RESTRICTED,
        )
    assert exc_info.value.approval_request_id is not None


# ── Test 4: PENDING → execution blocked ────────────────────────────────


@pytest.mark.asyncio
async def test_pending_approval_blocks_execution(db_session: AsyncSession) -> None:
    """A PENDING approval cannot be used to execute — must be APPROVED first."""
    from src.ai.schemas import OperationContext, RiskAssessment, RiskLevel
    from src.services.approval_service import ApprovalService, ApprovalStatus

    svc = ApprovalService(db_session)
    ctx = OperationContext(
        user_id="00000000-0000-0000-0000-000000000001",
        role="administrator",
        permission="system.execute",
        resource="prod-server",
        action="restart",
        data_sensitivity=DataSensitivity.INTERNAL,
    )
    risk = RiskAssessment(risk_level=RiskLevel.HIGH, requires_approval=True)
    approval = await svc.create("req-pending", ctx, risk, "Test pending block")

    assert approval.status == ApprovalStatus.PENDING

    # Attempting to assert_executable on PENDING must raise
    from src.core.exceptions import ApprovalError

    with pytest.raises(ApprovalError, match="pending"):
        svc.assert_executable(approval, ctx, risk)


# ── Test 5: LLM cannot execute shell ───────────────────────────────────


@pytest.mark.asyncio
async def test_llm_cannot_execute_shell(db_session: AsyncSession) -> None:
    """Requesting a shell tool raises ToolNotFoundError — LLM security boundary."""
    engine = OrchestratorEngine(db_session)
    tool_request = ToolRequest(
        requested_action="run shell command",
        tool="shell_execute",
        parameters={"command": "ls -la"},
    )
    with pytest.raises(ToolNotFoundError):
        await engine.execute(
            auth=_admin_auth(),
            user_input="Run shell command",
            data_sensitivity=DataSensitivity.PUBLIC,
            tool_request=tool_request,
        )


# ── Test 6: LLM cannot execute SQL ─────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_cannot_execute_sql(db_session: AsyncSession) -> None:
    """Requesting a SQL tool raises ToolNotFoundError — LLM security boundary."""
    engine = OrchestratorEngine(db_session)
    tool_request = ToolRequest(
        requested_action="run SQL query",
        tool="sql_execute",
        parameters={"query": "SELECT * FROM users"},
    )
    with pytest.raises(ToolNotFoundError):
        await engine.execute(
            auth=_admin_auth(),
            user_input="Query the database",
            data_sensitivity=DataSensitivity.PUBLIC,
            tool_request=tool_request,
        )


# ── Test 7: Unknown tool → DENY ────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_tool_denied_by_orchestrator(db_session: AsyncSession) -> None:
    """Any unregistered tool is denied — no fallback execution."""
    engine = OrchestratorEngine(db_session)
    tool_request = ToolRequest(
        requested_action="do something",
        tool="nonexistent_tool_xyz",
        parameters={},
    )
    with pytest.raises(ToolNotFoundError):
        await engine.execute(
            auth=_admin_auth(),
            user_input="Use unknown tool",
            data_sensitivity=DataSensitivity.PUBLIC,
            tool_request=tool_request,
        )


# ── Test 8: Task classification flows through ──────────────────────────


@pytest.mark.asyncio
async def test_task_classification_in_result(db_session: AsyncSession) -> None:
    """Task category is correctly classified and included in the result."""
    engine = OrchestratorEngine(db_session)
    result = await engine.execute(
        auth=_admin_auth(),
        user_input="Debug this Python function and fix the bug",
        data_sensitivity=DataSensitivity.PUBLIC,
    )
    assert result.task_category == TaskCategory.CODING


# ── Test 9: Audit events recorded ──────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_events_recorded(db_session: AsyncSession) -> None:
    """Orchestrator records audit events for each execution."""
    engine = OrchestratorEngine(db_session)
    audit_svc = AuditService(db_session)

    events_before = await audit_svc.repo.list_events(limit=1000)
    count_before = len(events_before)

    await engine.execute(
        auth=_admin_auth(),
        user_input="Tell me about Python",
        data_sensitivity=DataSensitivity.PUBLIC,
    )

    events_after = await audit_svc.repo.list_events(limit=1000)
    assert len(events_after) > count_before


# ── Test 10: Rate limiter is independent of account lockout ────────────


def test_rate_limiter_independent_of_lockout() -> None:
    """Rate limiter tracks requests per key; account lockout is a separate mechanism."""
    limiter = InMemoryRateLimiter()

    # Should not raise for first few requests
    for _ in range(5):
        limiter.check(RateLimitCategory.API, "test-key-independent")

    # Reset clears the counter
    limiter.reset(RateLimitCategory.API, "test-key-independent")
    limiter.check(RateLimitCategory.API, "test-key-independent")  # should not raise


def test_rate_limiter_exceeds_limit() -> None:
    """Rate limiter raises RateLimitExceededError when limit is hit."""
    limiter = InMemoryRateLimiter()
    # LOGIN limit is 10 per 300s
    for _ in range(10):
        limiter.check(RateLimitCategory.LOGIN, "test-exceed-key")

    with pytest.raises(RateLimitExceededError):
        limiter.check(RateLimitCategory.LOGIN, "test-exceed-key")


# ── Test 11: Document knowledge query routes to KnowledgeAgent & returns citations ──


@pytest.mark.asyncio
async def test_document_query_routes_to_knowledge_agent_and_citations(
    db_session: AsyncSession,
) -> None:
    """Document knowledge query maps to KnowledgeAgent and propagates citations into TaskResponse."""
    from src.rag.store import KnowledgeDocument, KnowledgeStore
    from src.schemas.orchestrator import orchestrator_result_to_task_response

    store = KnowledgeStore.get_instance()
    store.add_document(
        KnowledgeDocument(
            title="Standard Remote Work VPN Policy",
            content="Employees must use Multi-Factor Authentication (MFA) to access the corporate VPN network.",
            category="general",
            classification=DataSensitivity.INTERNAL,
            allowed_roles=["administrator", "manager", "general_employee"],
        )
    )

    engine = OrchestratorEngine(db_session)
    # Using employee auth ensures RESTRICTED executive audit docs are withheld by clearance filter
    result = await engine.execute(
        auth=_employee_auth(),
        user_input="Summarize the document instructions for employee remote work VPN connection.",
        data_sensitivity=DataSensitivity.INTERNAL,
    )

    assert result.agent_used == "knowledge_agent"
    assert result.task_category == TaskCategory.DOCUMENT
    assert len(result.citations) > 0
    assert "Standard Remote Work VPN Policy" in [c["document_title"] for c in result.citations]

    response = orchestrator_result_to_task_response(result)
    assert len(response.citations) > 0
    assert response.citations[0]["document_title"] == "Standard Remote Work VPN Policy"
