"""
ServerGen AI — Deterministic Risk Engine.

Multi-factor, rule-based risk assessment. The LLM never decides risk and tool
metadata can only *inform* it — this engine is the final authority.

Factors (each yields a level + a human-readable reason; the result is the highest):
  1. Data sensitivity        PUBLIC/INTERNAL→LOW, CONFIDENTIAL→MEDIUM, RESTRICTED→HIGH
  2. Operation type          QUERY/ANALYSIS→LOW, REPORT→MEDIUM, MODIFY/EXECUTE→HIGH
  3. Task category           SECURITY/OPERATIONS→MEDIUM (even when only discussing)
  4. Tool                    shell-like tools→HIGH, otherwise tool metadata impact
  5. Production impact       production-affecting MODIFY/EXECUTE→CRITICAL
  6. Administrative action   admin permissions→HIGH
  7. Combinations            CONFIDENTIAL+ with MODIFY/EXECUTE→CRITICAL

Reference outcomes: general information → LOW; confidential document analysis →
MEDIUM; security-configuration modification → HIGH; production-affecting
operation → CRITICAL.
"""

from __future__ import annotations

import logging

from src.ai.schemas import (
    DataSensitivity,
    OperationContext,
    OperationType,
    RiskAssessment,
    RiskLevel,
    TaskCategory,
    risk_at_least,
    sensitivity_at_least,
)

logger = logging.getLogger("servergen.risk")

_HIGH_RISK_TOOL_MARKERS = ("shell", "execute", "command", "deploy", "delete", "modify_system")
_ADMIN_PERMISSIONS = frozenset({"admin.manage", "user.write", "security.execute"})
_WRITE_ACTIONS = frozenset({"write", "execute", "delete", "modify"})
_ORDER = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}


def _higher_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    """Return the higher of two risk levels."""
    return a if _ORDER[a] >= _ORDER[b] else b


class RiskEngine:
    """Deterministic risk assessment engine (pure function of the OperationContext)."""

    def assess(self, context: OperationContext) -> RiskAssessment:
        """Evaluate an operation: returns the highest factor level and every contributing factor."""
        factors: list[str] = []
        max_risk = RiskLevel.LOW

        for level, factor in (
            self._assess_data_sensitivity(context),
            self._assess_operation_type(context),
            self._assess_task_category(context),
            self._assess_tool(context),
            self._assess_potential_impact(context),
            self._assess_production(context),
            self._assess_admin_actions(context),
            self._assess_combinations(context),
        ):
            if factor:
                factors.append(factor)
            max_risk = _higher_risk(max_risk, level)

        assessment = RiskAssessment(
            risk_level=max_risk,
            factors=factors,
            requires_approval=risk_at_least(max_risk, RiskLevel.HIGH),
            explanation=f"Risk: {max_risk.value} — {len(factors)} factor(s)",
        )
        logger.info(
            "Risk assessed: %s user=%s action=%s resource=%s",
            max_risk.value,
            context.user_id,
            context.action,
            context.resource,
        )
        return assessment

    # ── Individual factors ──────────────────────────────────────────────

    @staticmethod
    def _assess_data_sensitivity(context: OperationContext) -> tuple[RiskLevel, str]:
        match context.data_sensitivity:
            case DataSensitivity.RESTRICTED:
                return RiskLevel.HIGH, "Data classified as RESTRICTED"
            case DataSensitivity.CONFIDENTIAL:
                return RiskLevel.MEDIUM, "Data classified as CONFIDENTIAL"
            case _:
                return RiskLevel.LOW, ""

    @staticmethod
    def _assess_operation_type(context: OperationContext) -> tuple[RiskLevel, str]:
        op = context.operation_type
        if op in (OperationType.MODIFY, OperationType.EXECUTE):
            return RiskLevel.HIGH, f"Operation type: {op.value}"
        if op is OperationType.REPORT:
            return RiskLevel.MEDIUM, "Operation type: report generation"
        if context.action in _WRITE_ACTIONS:
            return RiskLevel.MEDIUM, f"Write/execute action: {context.action}"
        return RiskLevel.LOW, ""

    @staticmethod
    def _assess_task_category(context: OperationContext) -> tuple[RiskLevel, str]:
        if context.task_category is TaskCategory.SECURITY:
            return RiskLevel.MEDIUM, "Security-related task"
        if context.task_category is TaskCategory.OPERATIONS:
            return RiskLevel.MEDIUM, "Operations task"
        return RiskLevel.LOW, ""

    @staticmethod
    def _assess_tool(context: OperationContext) -> tuple[RiskLevel, str]:
        tool = context.tool.lower() if context.tool else ""
        if tool and any(marker in tool for marker in _HIGH_RISK_TOOL_MARKERS):
            return RiskLevel.HIGH, f"High-risk tool: {context.tool}"
        return RiskLevel.LOW, ""

    @staticmethod
    def _assess_potential_impact(context: OperationContext) -> tuple[RiskLevel, str]:
        impact = context.potential_impact.lower() if context.potential_impact else ""
        if not impact:
            return RiskLevel.LOW, ""
        label = f"Potential impact: {context.potential_impact}"
        if impact == "critical" or "irreversible" in impact or "destructive" in impact:
            return RiskLevel.CRITICAL, label
        if impact == "high" or "system-wide" in impact or "production" in impact:
            return RiskLevel.HIGH, label
        if impact == "medium" or "modif" in impact or "change" in impact:
            return RiskLevel.MEDIUM, label
        return RiskLevel.LOW, ""

    @staticmethod
    def _assess_production(context: OperationContext) -> tuple[RiskLevel, str]:
        if context.production_affecting:
            return RiskLevel.CRITICAL, "Operation affects production/plant systems"
        return RiskLevel.LOW, ""

    @staticmethod
    def _assess_admin_actions(context: OperationContext) -> tuple[RiskLevel, str]:
        if context.permission in _ADMIN_PERMISSIONS:
            return RiskLevel.HIGH, f"Administrative permission: {context.permission}"
        if context.permission == "approval.approve" and sensitivity_at_least(
            context.data_sensitivity, DataSensitivity.CONFIDENTIAL
        ):
            return RiskLevel.HIGH, "Approval on CONFIDENTIAL+ data"
        return RiskLevel.LOW, ""

    @staticmethod
    def _assess_combinations(context: OperationContext) -> tuple[RiskLevel, str]:
        changes_state = context.operation_type in (OperationType.MODIFY, OperationType.EXECUTE)
        if changes_state and sensitivity_at_least(
            context.data_sensitivity, DataSensitivity.CONFIDENTIAL
        ):
            return (
                RiskLevel.CRITICAL,
                f"{context.operation_type.value} on {context.data_sensitivity.value} data",
            )
        return RiskLevel.LOW, ""
