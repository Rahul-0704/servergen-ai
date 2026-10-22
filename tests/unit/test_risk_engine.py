"""
Phase D Tests — Data Sensitivity & Risk Engine.

Tests:
 1. DataSensitivity ordering
 2. RiskLevel ordering
 3. sensitivity_at_least comparisons
 4. risk_at_least comparisons
 5. DEFAULT_SENSITIVITY is safe
 6. RiskEngine: PUBLIC data → LOW risk
 7. RiskEngine: RESTRICTED data → CRITICAL risk (requires approval)
 8. RiskEngine: CONFIDENTIAL data → HIGH risk (requires approval)
 9. RiskEngine: high-risk tool → HIGH risk
10. RiskEngine: security task category → HIGH risk
11. RiskEngine: admin permission → HIGH risk
12. RiskEngine: irreversible impact → CRITICAL risk
13. RiskEngine: general read-only → LOW risk
14. OperationContext defaults are safe
"""

from __future__ import annotations

from src.ai.schemas import (
    DEFAULT_SENSITIVITY,
    DataSensitivity,
    OperationContext,
    RiskLevel,
    TaskCategory,
    risk_at_least,
    sensitivity_at_least,
)
from src.orchestrator.risk_engine import RiskEngine

# ── Test 1: Sensitivity ordering ────────────────────────────────────────


def test_sensitivity_ordering() -> None:
    """Sensitivity levels are ordered: PUBLIC < INTERNAL < CONFIDENTIAL < RESTRICTED."""
    assert sensitivity_at_least(DataSensitivity.RESTRICTED, DataSensitivity.PUBLIC)
    assert sensitivity_at_least(DataSensitivity.CONFIDENTIAL, DataSensitivity.INTERNAL)
    assert not sensitivity_at_least(DataSensitivity.PUBLIC, DataSensitivity.RESTRICTED)
    assert sensitivity_at_least(DataSensitivity.INTERNAL, DataSensitivity.INTERNAL)


# ── Test 2: Risk level ordering ─────────────────────────────────────────


def test_risk_ordering() -> None:
    """Risk levels are ordered: LOW < MEDIUM < HIGH < CRITICAL."""
    assert risk_at_least(RiskLevel.CRITICAL, RiskLevel.LOW)
    assert risk_at_least(RiskLevel.HIGH, RiskLevel.MEDIUM)
    assert not risk_at_least(RiskLevel.LOW, RiskLevel.HIGH)
    assert risk_at_least(RiskLevel.MEDIUM, RiskLevel.MEDIUM)


# ── Test 3-4: Comparison helpers ────────────────────────────────────────


def test_sensitivity_at_least_boundaries() -> None:
    """Boundary cases for sensitivity comparison."""
    assert sensitivity_at_least(DataSensitivity.PUBLIC, DataSensitivity.PUBLIC)
    assert sensitivity_at_least(DataSensitivity.RESTRICTED, DataSensitivity.RESTRICTED)
    assert not sensitivity_at_least(DataSensitivity.INTERNAL, DataSensitivity.CONFIDENTIAL)


def test_risk_at_least_boundaries() -> None:
    """Boundary cases for risk comparison."""
    assert risk_at_least(RiskLevel.LOW, RiskLevel.LOW)
    assert risk_at_least(RiskLevel.CRITICAL, RiskLevel.CRITICAL)
    assert not risk_at_least(RiskLevel.MEDIUM, RiskLevel.HIGH)


# ── Test 5: Safe defaults ──────────────────────────────────────────────


def test_default_sensitivity_is_safe() -> None:
    """Unknown sensitivity defaults to INTERNAL (not PUBLIC)."""
    assert DEFAULT_SENSITIVITY == DataSensitivity.INTERNAL


def test_operation_context_defaults() -> None:
    """OperationContext defaults to safe values."""
    ctx = OperationContext(user_id="u1", role="general_employee")
    assert ctx.data_sensitivity == DataSensitivity.INTERNAL
    assert ctx.task_category == TaskCategory.GENERAL


# ── Test 6: PUBLIC data → LOW risk ─────────────────────────────────────


def test_risk_public_data_low() -> None:
    """PUBLIC data with a read action should be LOW risk."""
    engine = RiskEngine()
    ctx = OperationContext(
        user_id="u1",
        role="general_employee",
        action="read",
        data_sensitivity=DataSensitivity.PUBLIC,
    )
    result = engine.assess(ctx)
    assert result.risk_level == RiskLevel.LOW
    assert result.requires_approval is False


# ── Test 7: RESTRICTED data → HIGH risk (read-only) / CRITICAL (write) ──


def test_risk_restricted_data_high_readonly() -> None:
    """RESTRICTED data with a read action → HIGH risk (requires approval)."""
    engine = RiskEngine()
    ctx = OperationContext(
        user_id="u1",
        role="administrator",
        resource="secret-document",
        action="read",
        data_sensitivity=DataSensitivity.RESTRICTED,
    )
    result = engine.assess(ctx)
    assert risk_at_least(result.risk_level, RiskLevel.HIGH)
    assert result.requires_approval is True
    assert any("RESTRICTED" in f for f in result.factors)


def test_risk_restricted_data_critical_modify() -> None:
    """RESTRICTED data with MODIFY operation → CRITICAL risk (combination factor)."""
    from src.ai.schemas import OperationType

    engine = RiskEngine()
    ctx = OperationContext(
        user_id="u1",
        role="administrator",
        resource="secret-document",
        action="write",
        data_sensitivity=DataSensitivity.RESTRICTED,
        operation_type=OperationType.MODIFY,
    )
    result = engine.assess(ctx)
    assert result.risk_level == RiskLevel.CRITICAL
    assert result.requires_approval is True


# ── Test 8: CONFIDENTIAL data → MEDIUM risk (read-only) ─────────────────


def test_risk_confidential_data_medium_readonly() -> None:
    """CONFIDENTIAL data with a read action → MEDIUM risk (no approval required)."""
    engine = RiskEngine()
    ctx = OperationContext(
        user_id="u1",
        role="manager",
        resource="hr-records",
        action="read",
        data_sensitivity=DataSensitivity.CONFIDENTIAL,
    )
    result = engine.assess(ctx)
    assert result.risk_level == RiskLevel.MEDIUM
    assert result.requires_approval is False


def test_risk_confidential_data_critical_modify() -> None:
    """CONFIDENTIAL data with MODIFY operation → CRITICAL (combination factor)."""
    from src.ai.schemas import OperationType

    engine = RiskEngine()
    ctx = OperationContext(
        user_id="u1",
        role="manager",
        resource="hr-records",
        action="write",
        data_sensitivity=DataSensitivity.CONFIDENTIAL,
        operation_type=OperationType.MODIFY,
    )
    result = engine.assess(ctx)
    assert result.risk_level == RiskLevel.CRITICAL
    assert result.requires_approval is True


# ── Test 9: High-risk tool → HIGH risk ─────────────────────────────────


def test_risk_high_risk_tool() -> None:
    """A tool with destructive capabilities raises risk level."""
    engine = RiskEngine()
    ctx = OperationContext(
        user_id="u1",
        role="it_operator",
        tool="shell_execute",
        action="execute",
        data_sensitivity=DataSensitivity.PUBLIC,
    )
    result = engine.assess(ctx)
    assert risk_at_least(result.risk_level, RiskLevel.HIGH)
    assert result.requires_approval is True


# ── Test 10: Security task → MEDIUM risk (query) / HIGH (modify) ────────


def test_risk_security_task_medium() -> None:
    """Security-related QUERY tasks are MEDIUM risk (not HIGH by default)."""
    engine = RiskEngine()
    ctx = OperationContext(
        user_id="u1",
        role="security_analyst",
        task_category=TaskCategory.SECURITY,
        data_sensitivity=DataSensitivity.PUBLIC,
    )
    result = engine.assess(ctx)
    assert result.risk_level == RiskLevel.MEDIUM


def test_risk_security_modify_high() -> None:
    """Security-related MODIFY task escalates to HIGH risk."""
    from src.ai.schemas import OperationType

    engine = RiskEngine()
    ctx = OperationContext(
        user_id="u1",
        role="security_analyst",
        task_category=TaskCategory.SECURITY,
        data_sensitivity=DataSensitivity.PUBLIC,
        operation_type=OperationType.MODIFY,
    )
    result = engine.assess(ctx)
    assert risk_at_least(result.risk_level, RiskLevel.HIGH)


# ── Test 11: Admin permission → HIGH risk ──────────────────────────────


def test_risk_admin_permission_high() -> None:
    """Administrative permissions raise risk."""
    engine = RiskEngine()
    ctx = OperationContext(
        user_id="u1",
        role="administrator",
        permission="admin.manage",
        data_sensitivity=DataSensitivity.PUBLIC,
    )
    result = engine.assess(ctx)
    assert risk_at_least(result.risk_level, RiskLevel.HIGH)


# ── Test 12: Irreversible impact → CRITICAL ────────────────────────────


def test_risk_irreversible_impact_critical() -> None:
    """Operations marked as irreversible are CRITICAL risk."""
    engine = RiskEngine()
    ctx = OperationContext(
        user_id="u1",
        role="it_operator",
        tool="data_wipe",
        potential_impact="irreversible data deletion",
        data_sensitivity=DataSensitivity.PUBLIC,
    )
    result = engine.assess(ctx)
    assert result.risk_level == RiskLevel.CRITICAL
    assert result.requires_approval is True


# ── Test 13: General read-only → LOW ───────────────────────────────────


def test_risk_general_readonly_low() -> None:
    """Simple read-only operation on public data is LOW risk."""
    engine = RiskEngine()
    ctx = OperationContext(
        user_id="u1",
        role="general_employee",
        action="read",
        resource="public-faq",
        data_sensitivity=DataSensitivity.PUBLIC,
        task_category=TaskCategory.GENERAL,
    )
    result = engine.assess(ctx)
    assert result.risk_level == RiskLevel.LOW
    assert result.requires_approval is False
