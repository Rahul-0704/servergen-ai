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
    "You are ServerGen AI, an enterprise-grade AI automation assistant running on local infrastructure. "
    "Provide accurate, authoritative, well-structured, and factual answers in clean Markdown. "
    "Use headers, bulleted points, and clear technical explanations. "
    "You cannot execute unverified commands, mutate systems, or access unauthorized data; never claim to have done so. "
    "When actions are required, explain the exact step-by-step procedure for an authorized human operator."
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
                f"=== AUTHORIZED ORGANIZATIONAL KNOWLEDGE ===\n"
                f"{request.rag_context}\n"
                f"===========================================\n\n"
                f"USER REQUEST:\n{prompt}\n\n"
                "RESPONSE INSTRUCTIONS:\n"
                "1. Answer thoroughly, factually, and accurately using the authorized organizational knowledge context above.\n"
                "2. Structure your response with clean Markdown: include an Executive Summary, Detailed Breakdown, and Operational Recommendations (if applicable).\n"
                "3. Explicitly cite the source document title(s) for the facts you provide (e.g., '[Source: <Document Title>]').\n"
                "4. If the context does not contain the required information, explicitly state that the internal documentation does not provide these details rather than speculating."
            )
            evidence.append("rag_knowledge_grounding")

        if request.tool_output:
            prompt = (
                f"{prompt}\n\n"
                f"VERIFIED TOOL RESULT:\n"
                f"```\n{request.tool_output}\n```\n"
                "INSTRUCTION: Incorporate and interpret this verified tool result in your response."
            )
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
        if response.success and response.model != request.model:
            warnings.append(
                f"Requested model '{request.model}' was not found locally; automatically fell back to active local model '{response.model}'."
            )

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

    system_prompt_suffix = "Deliver direct, structured, and logically rigorous answers with executive summaries and itemized breakdowns."

    @property
    def metadata(self) -> AgentMetadata:
        return AgentMetadata(
            name="general_agent",
            capability=AgentCapability.GENERAL,
            description="Handles general queries using the local LLM",
            required_permission="ai.execute",
        )


class KnowledgeAgent(Agent):
    """Document/knowledge questions. Synthesizes organizational knowledge."""

    system_prompt_suffix = "Synthesize organizational documents accurately. Cross-reference sections and cite specific source titles and classifications."
    advisory_warning = "knowledge_retrieval_advisory: answer grounded in available organizational knowledge documents"

    @property
    def metadata(self) -> AgentMetadata:
        return AgentMetadata(
            name="knowledge_agent",
            capability=AgentCapability.KNOWLEDGE,
            description="Document analysis and organizational knowledge synthesis",
            required_permission="document.read",
        )


class OperationsAgent(Agent):
    """Operational requests. ADVISORY ONLY — real execution arrives with Module 4."""

    system_prompt_suffix = "Structure operational guidance as an actionable runbook checklist with prerequisites, execution steps, and verification commands."
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

    system_prompt_suffix = "Provide defensive security analysis, threat mitigation advice, and audit posture assessments adhering to zero-trust principles."
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

    system_prompt_suffix = "Draft structured executive reports with clear sections: Executive Summary, Key Findings, Metrics/KPIs, and Recommended Next Steps."
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
