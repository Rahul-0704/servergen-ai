"""
ServerGen AI — AI/Orchestrator Schemas.

Pydantic models for data sensitivity, risk assessment, task classification,
and operation contexts. These form the shared vocabulary between the
orchestrator components.

IMPORTANT: Data sensitivity comes from trusted resource metadata — NOT from
the LLM. If sensitivity is unknown, the safer configured behavior applies.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

# ── Data Sensitivity Levels ─────────────────────────────────────────────


class DataSensitivity(StrEnum):
    """
    Data sensitivity classification.

    Applied by trusted metadata/policy — NEVER by the LLM.
    Unknown defaults to INTERNAL (safer default).
    """

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


# Ordered by increasing sensitivity for comparison
_SENSITIVITY_ORDER: dict[DataSensitivity, int] = {
    DataSensitivity.PUBLIC: 0,
    DataSensitivity.INTERNAL: 1,
    DataSensitivity.CONFIDENTIAL: 2,
    DataSensitivity.RESTRICTED: 3,
}

# Safe default when sensitivity is unknown
DEFAULT_SENSITIVITY = DataSensitivity.INTERNAL


def sensitivity_at_least(level: DataSensitivity, minimum: DataSensitivity) -> bool:
    """Check if a sensitivity level is at or above a minimum threshold."""
    return _SENSITIVITY_ORDER[level] >= _SENSITIVITY_ORDER[minimum]


# ── Risk Levels ─────────────────────────────────────────────────────────


class RiskLevel(StrEnum):
    """Risk assessment output levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_RISK_ORDER: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


def risk_at_least(level: RiskLevel, minimum: RiskLevel) -> bool:
    """Check if a risk level is at or above a minimum threshold."""
    return _RISK_ORDER[level] >= _RISK_ORDER[minimum]


# ── Risk Assessment ─────────────────────────────────────────────────────


class RiskAssessment(BaseModel):
    """
    Output of the deterministic RiskEngine.

    Risk is calculated from explicit rules — NEVER by the LLM.
    """

    risk_level: RiskLevel
    factors: list[str] = Field(
        default_factory=list,
        description="List of factors that contributed to the risk level",
    )
    requires_approval: bool = False
    explanation: str = ""


# ── Task Classification ────────────────────────────────────────────────


class TaskCategory(StrEnum):
    """Categories for user-submitted tasks."""

    GENERAL = "general"
    DOCUMENT = "document"
    CODING = "coding"
    OPERATIONS = "operations"
    SECURITY = "security"
    REPORTING = "reporting"


class OperationType(StrEnum):
    """
    What the request is trying to DO. Derived by deterministic rules — never by the
    LLM and never accepted from the client.
    """

    QUERY = "query"  # general information / simple question
    ANALYSIS = "analysis"  # document / cross-document analysis
    REPORT = "report"  # report generation
    MODIFY = "modify"  # configuration / policy / state change
    EXECUTE = "execute"  # operational execution (deploy, restart, run ...)


class TaskClassification(BaseModel):
    """Output of the TaskClassifier (validated before use)."""

    category: TaskCategory
    operation_type: OperationType = OperationType.QUERY
    production_affecting: bool = False
    rule_match_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Strength of the keyword-rule match. Informational only — NOT a trust signal.",
    )
    reasoning: str = ""


# ── Operation Context ──────────────────────────────────────────────────


class OperationContext(BaseModel):
    """
    Context for a requested operation, used by Policy and Risk engines.

    Collects all the attributes needed for deterministic security decisions.
    """

    user_id: str
    role: str
    permission: str = ""
    extra_permissions: list[str] = Field(
        default_factory=list,
        description="Additional permissions that must ALL be held (e.g. a tool's own permission)",
    )
    resource: str = ""
    action: str = ""
    agent: str = ""
    tool: str = ""
    data_sensitivity: DataSensitivity = DEFAULT_SENSITIVITY
    task_category: TaskCategory = TaskCategory.GENERAL
    operation_type: OperationType = OperationType.QUERY
    production_affecting: bool = False
    parameters: dict = Field(default_factory=dict)
    potential_impact: str = ""
