"""
ServerGen AI — Policy Engine.

Mandatory security boundary. Every protected agent execution, tool execution,
resource access, sensitive data access, administrative operation, and approval
action MUST pass through policy evaluation.

Policy evaluation considers: user, role, permission, resource, action, agent,
tool, data_sensitivity, risk_assessment.

Decisions: ALLOW / DENY / REQUIRE_APPROVAL

The policy engine is DETERMINISTIC. The LLM NEVER decides authorization.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import ClassVar

from src.ai.schemas import (
    DataSensitivity,
    OperationContext,
    OperationType,
    RiskAssessment,
    RiskLevel,
    risk_at_least,
    sensitivity_at_least,
)
from src.auth.permissions import SystemRole
from src.auth.rbac import AuthContext

logger = logging.getLogger("servergen.policy")


class PolicyDecision(StrEnum):
    """Possible outcomes of a policy evaluation."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class PolicyResult:
    """Result of a policy engine evaluation."""

    __slots__ = ("decision", "reason", "required_approval_level")

    def __init__(
        self,
        decision: PolicyDecision,
        reason: str = "",
        required_approval_level: str = "",
    ) -> None:
        self.decision = decision
        self.reason = reason
        self.required_approval_level = required_approval_level

    @property
    def is_allowed(self) -> bool:
        return self.decision == PolicyDecision.ALLOW

    @property
    def is_denied(self) -> bool:
        return self.decision == PolicyDecision.DENY

    @property
    def requires_approval(self) -> bool:
        return self.decision == PolicyDecision.REQUIRE_APPROVAL

    def __repr__(self) -> str:
        return f"<PolicyResult(decision={self.decision.value!r}, reason={self.reason!r})>"


class PolicyEngine:
    """
    Deterministic policy engine — mandatory security boundary.

    Every operation goes through evaluate() which checks:
    1. Permission-based access (RBAC)
    2. Data sensitivity rules
    3. Risk-based escalation
    4. Tool/agent restrictions
    """

    def evaluate(
        self,
        auth: AuthContext,
        context: OperationContext,
        risk: RiskAssessment,
        *,
        approval_granted: bool = False,
    ) -> PolicyResult:
        """
        Evaluate whether an operation should be allowed.

        Checks are applied in order; the first DENY or REQUIRE_APPROVAL
        short-circuits the evaluation.

        ``approval_granted`` is set ONLY when resuming an operation whose approval
        record was verified (status, expiry, single-use, fingerprint). It satisfies
        a REQUIRE_APPROVAL outcome but can never override a DENY.
        """
        # ── Check 1: Permission-based access (RBAC) ────────────────
        result = self._check_permission(auth, context)
        if not result.is_allowed:
            return result

        # ── Check 2: Data sensitivity restrictions ─────────────────
        result = self._check_data_sensitivity(auth, context)
        if not result.is_allowed:
            return result

        # ── Check 3: Tool/agent-specific restrictions ──────────────
        result = self._check_tool_restrictions(auth, context)
        if not result.is_allowed:
            return result

        # ── Check 4: Risk-based escalation (last: DENY must win) ───
        result = self._check_risk_escalation(auth, context, risk)
        if result.requires_approval:
            if self._is_explicitly_exempt(auth, context):
                logger.info(
                    "Policy exemption applied: role=%s resource=%s", auth.role, context.resource
                )
            elif approval_granted:
                logger.info("Policy: approval satisfied for %s", context.resource)
            else:
                return result

        logger.info(
            "Policy ALLOW: user=%s role=%s action=%s resource=%s",
            context.user_id,
            context.role,
            context.action,
            context.resource,
        )
        return PolicyResult(PolicyDecision.ALLOW, reason="All policy checks passed")

    # ── Explicit allow rules (spec: HIGH/CRITICAL need approval unless a rule says otherwise) ──

    # (role, permission, resource-prefix): routine user administration by administrators is
    # permitted without a second approver; it is still RBAC-checked and fully audited.
    _EXEMPTIONS: ClassVar[tuple[tuple[str, str, str], ...]] = (
        (SystemRole.ADMIN.value, "user.write", "user:"),
    )

    def _is_explicitly_exempt(self, auth: AuthContext, context: OperationContext) -> bool:
        return any(
            auth.role == role
            and context.permission == permission
            and context.resource.startswith(prefix)
            for role, permission, prefix in self._EXEMPTIONS
        )

    # ── Individual policy checks ────────────────────────────────────

    def _check_permission(self, auth: AuthContext, context: OperationContext) -> PolicyResult:
        """Check the primary permission and every additional (tool/agent) permission."""
        required = [p for p in (context.permission, *context.extra_permissions) if p]
        for permission in required:
            if not auth.has_permission(permission):
                reason = f"Role '{auth.role}' lacks permission '{permission}'"
                logger.warning("Policy DENY (permission): %s", reason)
                return PolicyResult(PolicyDecision.DENY, reason=reason)
        return PolicyResult(PolicyDecision.ALLOW)

    def _check_data_sensitivity(self, auth: AuthContext, context: OperationContext) -> PolicyResult:
        """
        Apply data-sensitivity-based restrictions.

        - RESTRICTED data: only ADMIN and SECURITY_ANALYST can access
        - CONFIDENTIAL data: GENERAL_EMPLOYEE cannot access
        """
        sensitivity = context.data_sensitivity

        if sensitivity == DataSensitivity.RESTRICTED:
            allowed_roles = {
                SystemRole.ADMIN.value,
                SystemRole.MANAGER.value,
                SystemRole.SECURITY_ANALYST.value,
            }
            if auth.role not in allowed_roles:
                reason = f"Role '{auth.role}' cannot access RESTRICTED data"
                logger.warning("Policy DENY (sensitivity): %s", reason)
                return PolicyResult(PolicyDecision.DENY, reason=reason)

        if (
            sensitivity_at_least(sensitivity, DataSensitivity.CONFIDENTIAL)
            and auth.role == SystemRole.GENERAL_EMPLOYEE.value
        ):
            reason = "GENERAL_EMPLOYEE cannot access CONFIDENTIAL+ data"
            logger.warning("Policy DENY (sensitivity): %s", reason)
            return PolicyResult(PolicyDecision.DENY, reason=reason)

        return PolicyResult(PolicyDecision.ALLOW)

    def _check_risk_escalation(
        self,
        auth: AuthContext,
        context: OperationContext,
        risk: RiskAssessment,
    ) -> PolicyResult:
        """
        Escalate to REQUIRE_APPROVAL for HIGH/CRITICAL risk operations.

        ADMIN can directly execute MEDIUM risk operations.
        HIGH/CRITICAL always requires approval (even for ADMIN).
        """
        # Administrator has supreme clearance: routine queries and non-destructive operations
        # do not require a second approver unless explicit RESTRICTED classification is declared
        if (
            auth.role == SystemRole.ADMIN.value
            and context.data_sensitivity != DataSensitivity.RESTRICTED
            and context.operation_type not in (OperationType.MODIFY, OperationType.EXECUTE)
            and context.action not in ("execute", "modify", "write", "delete")
            and not context.production_affecting
        ):
            return PolicyResult(
                PolicyDecision.ALLOW,
                reason="Administrator clearance: unrestricted query execution permitted",
            )

        if risk_at_least(risk.risk_level, RiskLevel.CRITICAL):
            return PolicyResult(
                PolicyDecision.REQUIRE_APPROVAL,
                reason=f"CRITICAL risk: {', '.join(risk.factors)}",
                required_approval_level="CRITICAL",
            )

        if risk_at_least(risk.risk_level, RiskLevel.HIGH):
            return PolicyResult(
                PolicyDecision.REQUIRE_APPROVAL,
                reason=f"HIGH risk: {', '.join(risk.factors)}",
                required_approval_level="HIGH",
            )

        return PolicyResult(PolicyDecision.ALLOW)

    def _check_tool_restrictions(
        self, auth: AuthContext, context: OperationContext
    ) -> PolicyResult:
        """
        Apply tool-specific restrictions.

        Certain tools/agents require specific roles.
        """
        tool = context.tool.lower() if context.tool else ""

        # System execution tools require IT_OPERATOR or ADMIN
        system_tools = {"shell", "command", "deploy", "system_exec"}
        if any(t in tool for t in system_tools):
            allowed_roles = {
                SystemRole.ADMIN.value,
                SystemRole.IT_OPERATOR.value,
            }
            if auth.role not in allowed_roles:
                reason = f"Tool '{context.tool}' restricted to ADMIN/IT_OPERATOR, got '{auth.role}'"
                logger.warning("Policy DENY (tool): %s", reason)
                return PolicyResult(PolicyDecision.DENY, reason=reason)

        return PolicyResult(PolicyDecision.ALLOW)
