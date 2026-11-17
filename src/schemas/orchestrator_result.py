"""
ServerGen AI — Orchestrator Result Schema.

Pydantic model for OrchestratorResult to ensure type safety
and proper attribute access.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OrchestratorResult(BaseModel):
    """Result of an orchestrated task execution."""

    request_id: str
    task_category: str
    risk_level: str
    policy_decision: str
    model_used: str
    content: str
    verification_status: str
    approval_id: str | None = None
    tool_used: str = ""
    tool_output: str = ""
    success: bool
    error: str = ""

    # ── Enriched fields from the updated architecture ────────────────
    agent_used: str = ""
    operation_type: str = ""
    data_sensitivity: str = ""
    production_affecting: bool = False
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    grounded_sources: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
