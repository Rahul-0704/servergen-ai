"""
Phase E Tests — Policy Engine.

Tests:
 1. ALLOW: valid permission + low risk → ALLOW
 2. DENY: missing permission → DENY
 3. DENY: GENERAL_EMPLOYEE + CONFIDENTIAL data → DENY
 4. DENY: non-admin/security + RESTRICTED data → DENY
 5. ALLOW: ADMIN + RESTRICTED data → passes sensitivity check
 6. REQUIRE_APPROVAL: HIGH risk → REQUIRE_APPROVAL
 7. REQUIRE_APPROVAL: CRITICAL risk → REQUIRE_APPROVAL
 8. DENY: restricted tool + wrong role → DENY
 9. ALLOW: shell tool + IT_OPERATOR → passes tool check
10. ALLOW: no permission required → ALLOW
11. Policy is deterministic (same input → same output)
"""

from __future__ import annotations

from src.ai.schemas import (
    DataSensitivity,
    OperationContext,
    RiskAssessment,
    RiskLevel,
)
from src.auth.policy import PolicyDecision, PolicyEngine
from src.auth.rbac import AuthContext


def _low_risk() -> RiskAssessment:
    return RiskAssessment(risk_level=RiskLevel.LOW)


def _high_risk() -> RiskAssessment:
    return RiskAssessment(
        risk_level=RiskLevel.HIGH,
        factors=["test-high-risk"],
        requires_approval=True,
    )


def _critical_risk() -> RiskAssessment:
    return RiskAssessment(
        risk_level=RiskLevel.CRITICAL,
        factors=["test-critical"],
        requires_approval=True,
    )


def _admin_context() -> AuthContext:
    return AuthContext(
        user_id="admin-1",
        role="administrator",
        permissions={
            "admin.manage",
            "document.read",
            "document.write",
            "system.read",
            "system.execute",
            "security.read",
            "security.execute",
            "report.generate",
            "approval.approve",
            "user.read",
            "user.write",
            "ai.execute",
            "ai.read",
            "audit.read",
        },
    )


def _employee_context() -> AuthContext:
    return AuthContext(
        user_id="emp-1",
        role="general_employee",
        permissions={"document.read", "ai.execute", "ai.read"},
    )


def _it_operator_context() -> AuthContext:
    return AuthContext(
        user_id="it-1",
        role="it_operator",
        permissions={
            "document.read",
            "document.write",
            "system.read",
            "system.execute",
            "report.generate",
            "user.read",
            "ai.execute",
            "ai.read",
            "audit.read",
        },
    )


engine = PolicyEngine()


# ── Test 1: ALLOW with valid permission + low risk ─────────────────────


def test_policy_allow_valid_permission() -> None:
    """User with correct permission + low risk → ALLOW."""
    ctx = OperationContext(
        user_id="admin-1",
        role="administrator",
        permission="document.read",
        action="read",
        data_sensitivity=DataSensitivity.PUBLIC,
    )
    result = engine.evaluate(_admin_context(), ctx, _low_risk())
    assert result.decision == PolicyDecision.ALLOW


# ── Test 2: DENY when missing permission ───────────────────────────────


def test_policy_deny_missing_permission() -> None:
    """User without required permission → DENY."""
    ctx = OperationContext(
        user_id="emp-1",
        role="general_employee",
        permission="admin.manage",
        action="manage",
    )
    result = engine.evaluate(_employee_context(), ctx, _low_risk())
    assert result.decision == PolicyDecision.DENY
    assert "lacks permission" in result.reason


# ── Test 3: DENY GENERAL_EMPLOYEE + CONFIDENTIAL ──────────────────────


def test_policy_deny_employee_confidential() -> None:
    """GENERAL_EMPLOYEE cannot access CONFIDENTIAL data."""
    ctx = OperationContext(
        user_id="emp-1",
        role="general_employee",
        permission="document.read",
        action="read",
        data_sensitivity=DataSensitivity.CONFIDENTIAL,
    )
    result = engine.evaluate(_employee_context(), ctx, _low_risk())
    assert result.decision == PolicyDecision.DENY
    assert "CONFIDENTIAL" in result.reason


# ── Test 4: DENY non-admin + RESTRICTED ────────────────────────────────


def test_policy_deny_non_admin_restricted() -> None:
    """Non-admin/security roles cannot access RESTRICTED data."""
    ctx = OperationContext(
        user_id="it-1",
        role="it_operator",
        permission="system.read",
        action="read",
        data_sensitivity=DataSensitivity.RESTRICTED,
    )
    result = engine.evaluate(_it_operator_context(), ctx, _low_risk())
    assert result.decision == PolicyDecision.DENY
    assert "RESTRICTED" in result.reason


# ── Test 5: ALLOW ADMIN + RESTRICTED (passes sensitivity) ─────────────


def test_policy_allow_admin_restricted_sensitivity() -> None:
    """ADMIN CAN access RESTRICTED data (passes sensitivity check)."""
    ctx = OperationContext(
        user_id="admin-1",
        role="administrator",
        permission="document.read",
        action="read",
        data_sensitivity=DataSensitivity.RESTRICTED,
    )
    # Low risk so no escalation
    result = engine.evaluate(_admin_context(), ctx, _low_risk())
    assert result.decision == PolicyDecision.ALLOW


# ── Test 6: REQUIRE_APPROVAL for HIGH risk ─────────────────────────────


def test_policy_require_approval_high_risk() -> None:
    """HIGH risk operations → REQUIRE_APPROVAL."""
    ctx = OperationContext(
        user_id="admin-1",
        role="administrator",
        permission="system.execute",
        action="execute",
        data_sensitivity=DataSensitivity.PUBLIC,
    )
    result = engine.evaluate(_admin_context(), ctx, _high_risk())
    assert result.decision == PolicyDecision.REQUIRE_APPROVAL
    assert result.required_approval_level == "HIGH"


# ── Test 7: REQUIRE_APPROVAL for CRITICAL risk ────────────────────────


def test_policy_require_approval_critical_risk() -> None:
    """CRITICAL risk operations → REQUIRE_APPROVAL."""
    ctx = OperationContext(
        user_id="admin-1",
        role="administrator",
        permission="admin.manage",
        action="execute",
    )
    result = engine.evaluate(_admin_context(), ctx, _critical_risk())
    assert result.decision == PolicyDecision.REQUIRE_APPROVAL
    assert result.required_approval_level == "CRITICAL"


# ── Test 8: DENY restricted tool + wrong role ──────────────────────────


def test_policy_deny_restricted_tool_wrong_role() -> None:
    """Shell tools are restricted to ADMIN/IT_OPERATOR."""
    ctx = OperationContext(
        user_id="emp-1",
        role="general_employee",
        permission="ai.execute",
        tool="shell_execute",
        action="execute",
        data_sensitivity=DataSensitivity.PUBLIC,
    )
    result = engine.evaluate(_employee_context(), ctx, _low_risk())
    assert result.decision == PolicyDecision.DENY
    assert "restricted" in result.reason.lower()


# ── Test 9: ALLOW shell tool + IT_OPERATOR ─────────────────────────────


def test_policy_allow_shell_tool_it_operator() -> None:
    """IT_OPERATOR CAN use shell tools (passes tool check)."""
    ctx = OperationContext(
        user_id="it-1",
        role="it_operator",
        permission="system.execute",
        tool="shell_execute",
        action="execute",
        data_sensitivity=DataSensitivity.PUBLIC,
    )
    # Low risk so no escalation
    result = engine.evaluate(_it_operator_context(), ctx, _low_risk())
    assert result.decision == PolicyDecision.ALLOW


# ── Test 10: ALLOW when no permission required ─────────────────────────


def test_policy_allow_no_permission_required() -> None:
    """When no specific permission is required, permission check passes."""
    ctx = OperationContext(
        user_id="emp-1",
        role="general_employee",
        action="read",
        data_sensitivity=DataSensitivity.PUBLIC,
    )
    result = engine.evaluate(_employee_context(), ctx, _low_risk())
    assert result.decision == PolicyDecision.ALLOW


# ── Test 11: Policy is deterministic ───────────────────────────────────


def test_policy_is_deterministic() -> None:
    """Same input → same output (policy is deterministic)."""
    ctx = OperationContext(
        user_id="emp-1",
        role="general_employee",
        permission="admin.manage",
        action="manage",
    )
    result1 = engine.evaluate(_employee_context(), ctx, _low_risk())
    result2 = engine.evaluate(_employee_context(), ctx, _low_risk())
    assert result1.decision == result2.decision
    assert result1.reason == result2.reason
