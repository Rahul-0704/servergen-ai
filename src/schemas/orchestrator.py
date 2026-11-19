"""
ServerGen AI — Orchestrator API Schemas.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.ai.schemas import DataSensitivity


class TaskRequest(BaseModel):
    """User-submitted AI task request."""

    input: str = Field(..., min_length=1, max_length=4000)
    data_sensitivity: DataSensitivity = DataSensitivity.INTERNAL
    model: str | None = Field(default=None, description="Optional target model name")
    tool: str | None = Field(default=None, description="Optional tool name to invoke")
    tool_parameters: dict = Field(default_factory=dict)
    structured: bool = Field(
        default=False,
        description="Request JSON-schema constrained structured decoding from model",
    )
    approval_id: str | None = Field(
        default=None,
        description="Optional ID of an approved authorization ticket satisfying policy approval",
    )


class TaskResponse(BaseModel):
    """Response from the orchestrator."""

    request_id: str
    task_category: str
    risk_level: str
    policy_decision: str
    model_used: str
    content: str
    verification_status: str
    tool_used: str = ""
    tool_output: str = ""
    success: bool
    error: str = ""
    approval_id: str | None = None

    # ── Enriched fields ──────────────────────────────────────────────
    agent_used: str = ""
    operation_type: str = ""
    data_sensitivity: str = ""
    production_affecting: bool = False
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    grounded_sources: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)


# OrchestratorResult is alias for TaskResponse
OrchestratorResult = TaskResponse


def orchestrator_result_to_task_response(result: TaskResponse) -> TaskResponse:
    return result


def _old_orchestrator_result_to_task_response(result: TaskResponse) -> TaskResponse:
    """Convert OrchestratorResult to TaskResponse."""
    return TaskResponse(
        request_id=result.request_id,
        task_category=result.task_category,
        risk_level=result.risk_level,
        policy_decision=result.policy_decision,
        model_used=result.model_used,
        content=result.content,
        verification_status=result.verification_status,
        tool_used=result.tool_used,
        tool_output=result.tool_output,
        success=result.success,
        error=result.error,
        approval_id=result.approval_id,
        agent_used=result.agent_used,
        operation_type=result.operation_type,
        data_sensitivity=result.data_sensitivity,
        production_affecting=result.production_affecting,
        evidence=result.evidence,
        warnings=result.warnings,
        artifacts=result.artifacts,
        grounded_sources=getattr(result, "grounded_sources", []),
        citations=getattr(result, "citations", []),
    )
