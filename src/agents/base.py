"""
ServerGen AI — Agent Abstractions.

Agents are high-level task handlers. They shape the prompt for a task type and
call the LLM provider they are GIVEN by the orchestrator. They NEVER execute
shell/SQL/filesystem/network operations and never self-authorize: the
orchestrator has already passed identity, RBAC, risk and policy before an agent
runs, and the agent's own ``required_permission`` is part of that policy check.

TRUST MODEL: results carry ``evidence`` and ``warnings`` — never an LLM-reported
confidence. Whether a result may be relied upon is decided by deterministic
verification, not by the model.

Operations/Security/Reporting/Knowledge agents here are deliberately thin,
advisory-only implementations that define the interface for Modules 3-6.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.ai.providers.base import LLMRequest, ModelProvider
from src.ai.schemas import OperationType, TaskCategory


class AgentCapability(StrEnum):
    GENERAL = "general"
    KNOWLEDGE = "knowledge"
    OPERATIONS = "operations"
    SECURITY = "security"
    REPORTING = "reporting"


class AgentStatus(StrEnum):
    """Outcome of an agent execution."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AgentMetadata(BaseModel):
    name: str
    capability: AgentCapability
    description: str
    required_permission: str = ""


class StructuredTaskOutput(BaseModel):
    """Standard structured output schema for constrained AI inference."""

    summary: str = Field(description="Direct response summary")
    details: list[str] = Field(default_factory=list, description="Key details, steps, or findings")
    action_items: list[str] = Field(
        default_factory=list, description="Recommended operational action items"
    )


class AgentRequest(BaseModel):
    """Everything an agent needs; assembled by the orchestrator after policy approval."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    task: str
    model: str
    category: TaskCategory = TaskCategory.GENERAL
    tool_output: str = ""
    rag_context: str = ""
    max_tokens: int = 1024
    structured: bool = False
    schema_model: Any = None


class AgentExecutionResult(BaseModel):
    """
    Structured agent result. Deliberately has NO ``confidence`` field.

    ``evidence`` records what the output is based on (model, tool output, token
    counts); ``warnings`` records limits the reader must know about.
    """

    success: bool
    output: str = ""
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    status: AgentStatus
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    execution_metadata: dict[str, Any] = Field(default_factory=dict)


_BASE_SYSTEM_PROMPT = (
    "You are a secure enterprise AI assistant running inside a private, audited system. "
    "Give factual, concise answers. You cannot execute commands, access files, query "
    "databases or call external systems; never claim to have done so. If a request would "
    "require such an action, explain the steps a human operator should take instead."
)


class Agent(ABC):
    """Abstract base for all agents."""

    system_prompt_suffix: str = ""
    advisory_warning: str = ""

    @property
    @abstractmethod
    def metadata(self) -> AgentMetadata:
        """Agent metadata including capability and required permission."""

    async def execute(self, request: AgentRequest, provider: ModelProvider) -> AgentExecutionResult:
        """Run the task through the provider and return a structured, evidence-bearing result."""
        prompt = request.task
        evidence: list[str] = []
        if request.rag_context:
            prompt = (
                f"ORGANIZATIONAL KNOWLEDGE CONTEXT:\n{request.rag_context}\n\n"
                f"USER QUESTION / TASK:\n{prompt}\n\n"
                "INSTRUCTION: Answer using the organizational knowledge context above whenever relevant. "
                "Be direct, factual, and clear."
            )
            evidence.append("rag_knowledge_grounding")

        if request.tool_output:
            prompt = f"{prompt}\n\nTool result (verified, read-only): {request.tool_output}"
            evidence.append("tool_output_included")

        system_prompt = f"{_BASE_SYSTEM_PROMPT} {self.system_prompt_suffix}".strip()
        llm_req = LLMRequest(
            model=request.model,
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=request.max_tokens,
        )

        artifacts: list[dict[str, Any]] = []
        if request.structured:
            target_schema = request.schema_model or StructuredTaskOutput
            structured_data, response = await provider.generate_structured(
                llm_req, schema=target_schema
            )
            if structured_data is not None:
                artifacts.append(structured_data.model_dump())
                evidence.append("structured_schema_validated")
                output_content = json.dumps(structured_data.model_dump(), indent=2)
            else:
                output_content = response.content
        else:
            response = await provider.generate(llm_req)
            output_content = response.content

        meta = {
            "agent": self.metadata.name,
            "model": response.model,
            "provider": response.provider,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "latency_ms": round(response.latency_ms, 1),
        }
        warnings = [self.advisory_warning] if self.advisory_warning else []

        if not response.success:
            user_msg = (
                f"Model execution failed ({response.error}). "
                "The local AI runtime is currently unavailable or encountered an error. "
                "Ensure the Ollama service is active and the requested model is pulled."
            )
            return AgentExecutionResult(
                success=False,
                output=user_msg,
                status=AgentStatus.FAILED,
                evidence=evidence,
                warnings=[*warnings, f"model_error: {response.error}"],
                execution_metadata=meta,
            )

        evidence.extend([f"model={response.model}", f"provider={response.provider}"])
        return AgentExecutionResult(
            success=True,
            output=output_content,
            artifacts=artifacts,
            status=AgentStatus.SUCCEEDED,
            evidence=evidence,
            warnings=[*warnings, "llm_output_is_unverified_text"],
            execution_metadata=meta,
        )


class GeneralAgent(Agent):
    """Handles general-purpose queries via the local LLM."""

    @property
    def metadata(self) -> AgentMetadata:
        return AgentMetadata(
            name="general_agent",
            capability=AgentCapability.GENERAL,
            description="Handles general queries using the local LLM",
            required_permission="ai.execute",
        )


class KnowledgeAgent(Agent):
    """Document/knowledge questions. RAG retrieval arrives with Module 3."""

    system_prompt_suffix = "Focus on analysing and summarising text the user supplies."
    advisory_warning = "knowledge_retrieval_not_available: answers use only the supplied text"

    @property
    def metadata(self) -> AgentMetadata:
        return AgentMetadata(
            name="knowledge_agent",
            capability=AgentCapability.KNOWLEDGE,
            description="Document analysis (interface for Module 3 — RAG)",
            required_permission="document.read",
        )


class OperationsAgent(Agent):
    """Operational requests. ADVISORY ONLY — real execution arrives with Module 4."""

    system_prompt_suffix = "Provide operational guidance as a checklist for a human operator."
    advisory_warning = "advisory_only: no operational action was executed"

    @property
    def metadata(self) -> AgentMetadata:
        return AgentMetadata(
            name="operations_agent",
            capability=AgentCapability.OPERATIONS,
            description="Operational guidance (interface for Module 4)",
            required_permission="system.read",
        )


class SecurityAgent(Agent):
    """Security requests. ADVISORY ONLY — real tooling arrives with Module 5."""

    system_prompt_suffix = "Provide defensive security guidance only; never offensive instructions."
    advisory_warning = "advisory_only: no security action was executed"

    @property
    def metadata(self) -> AgentMetadata:
        return AgentMetadata(
            name="security_agent",
            capability=AgentCapability.SECURITY,
            description="Security guidance (interface for Module 5)",
            required_permission="security.read",
        )


class ReportingAgent(Agent):
    """Report drafting. Data-backed reporting arrives with Module 6."""

    system_prompt_suffix = "Draft a clear, structured report from the supplied information only."
    advisory_warning = "draft_only: no enterprise data sources were queried"

    @property
    def metadata(self) -> AgentMetadata:
        return AgentMetadata(
            name="reporting_agent",
            capability=AgentCapability.REPORTING,
            description="Report drafting (interface for Module 6)",
            required_permission="report.generate",
        )


class AgentRegistry:
    """Registry of available agents."""

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        self._agents[agent.metadata.name] = agent

    def get(self, name: str) -> Agent | None:
        return self._agents.get(name)

    def find_by_capability(self, capability: AgentCapability) -> Agent | None:
        """First registered agent offering ``capability`` (registration order)."""
        for agent in self._agents.values():
            if agent.metadata.capability == capability:
                return agent
        return None

    def list_agents(self) -> list[AgentMetadata]:
        return [a.metadata for a in self._agents.values()]


class AgentSelector:
    """
    Deterministic agent selection.

    Plain information requests stay with the general agent even when they mention
    operations/security topics; specialised agents handle state-changing
    (MODIFY/EXECUTE), reporting and document work.
    """

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    @staticmethod
    def _capability_for(category: TaskCategory, operation_type: OperationType) -> AgentCapability:
        if operation_type in (OperationType.MODIFY, OperationType.EXECUTE):
            if category is TaskCategory.SECURITY:
                return AgentCapability.SECURITY
            return AgentCapability.OPERATIONS
        if operation_type is OperationType.REPORT:
            return AgentCapability.REPORTING
        if operation_type is OperationType.ANALYSIS:
            return AgentCapability.KNOWLEDGE
        return AgentCapability.GENERAL

    def select(
        self,
        task_category: TaskCategory,
        operation_type: OperationType = OperationType.QUERY,
    ) -> Agent:
        """Select the agent for a task, falling back to the general agent."""
        agent = self.registry.find_by_capability(
            self._capability_for(task_category, operation_type)
        ) or self.registry.find_by_capability(AgentCapability.GENERAL)
        if agent is None:
            msg = "No agents registered"
            raise RuntimeError(msg)
        return agent


def build_default_agent_registry() -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(GeneralAgent())
    registry.register(KnowledgeAgent())
    registry.register(OperationsAgent())
    registry.register(SecurityAgent())
    registry.register(ReportingAgent())
    return registry
