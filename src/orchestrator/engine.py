"""
ServerGen AI — Orchestrator Engine.

Coordinates the full request pipeline:
  Auth → RBAC → TaskClassification → Sensitivity → Risk → Policy
  → Agent Selection → Model Routing → LLM Execution → Verification → Audit

The engine is a coordinator — it delegates to specialized components.
It does NOT become a god class: each concern lives in its own module.

LLM SECURITY BOUNDARY:
  LLM output → Pydantic validation → ToolSelector → PolicyEngine → Tool
  LLM NEVER directly executes shell/SQL/filesystem/network commands.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.base import (
    AgentRequest,
    AgentSelector,
    build_default_agent_registry,
)
from src.ai.model_registry import ModelRouter, build_default_registry
from src.ai.schemas import (
    DataSensitivity,
    OperationContext,
)
from src.auth.policy import PolicyDecision, PolicyEngine
from src.auth.rbac import AuthContext
from src.core.exceptions import (
    ApprovalRequiredError,
    PolicyDeniedError,
    ToolNotFoundError,
)
from src.orchestrator.risk_engine import RiskEngine
from src.orchestrator.sensitivity import SensitivityResolver
from src.orchestrator.task_classifier import TaskClassifier
from src.orchestrator.verifier import Verifier
from src.rag.retriever import RoleFilteredRetriever
from src.rate_limiting.memory import RateLimitCategory, get_rate_limiter
from src.schemas.orchestrator_result import OrchestratorResult
from src.services.approval_service import ApprovalService
from src.services.audit_service import AuditEventType, AuditService
from src.tools.base import ToolRequest, ToolSelector, build_default_tool_registry

logger = logging.getLogger("servergen.orchestrator")

# Singletons built once at startup
_registry = build_default_registry()
_agent_registry = build_default_agent_registry()
_tool_registry = build_default_tool_registry()


class OrchestratorEngine:
    """
    Central coordinator for AI task execution.

    Components:
      TaskClassifier → SensitivityResolver → RiskEngine → PolicyEngine
      → AgentSelector → ModelRouter → ToolSelector → ApprovalService
      → Verifier → AuditService
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.classifier = TaskClassifier()
        self.sensitivity_resolver = SensitivityResolver()
        self.risk_engine = RiskEngine()
        self.policy_engine = PolicyEngine()
        self.model_router = ModelRouter(_registry)
        self.agent_selector = AgentSelector(_agent_registry)
        self.tool_selector = ToolSelector(_tool_registry)
        self.verifier = Verifier()
        self.rag_retriever = RoleFilteredRetriever()
        self.audit = AuditService(db)
        self.approval_svc = ApprovalService(db)

    async def execute(
        self,
        auth: AuthContext,
        user_input: str,
        data_sensitivity: DataSensitivity = DataSensitivity.INTERNAL,
        tool_request: ToolRequest | None = None,
        request_id: str | None = None,
        structured: bool = False,
    ) -> OrchestratorResult:
        """
        Execute a user task through the full security pipeline.

        Returns OrchestratorResult. Never raises unhandled exceptions.
        """
        req_id = request_id or str(uuid.uuid4())

        # ── Step 1: Rate limiting check ──────────────────────────────
        limiter = get_rate_limiter()
        limiter.check(RateLimitCategory.LLM, auth.user_id)

        # ── Step 2: Task Classification (deterministic rules) ────────
        classification = self.classifier.classify(user_input)
        task_category = classification.category
        operation_type = classification.operation_type
        production_affecting = classification.production_affecting

        # ── Step 3: Server-side Sensitivity Resolution ───────────────
        # Client-declared sensitivity can only RAISE, never lower the result.
        sensitivity = self.sensitivity_resolver.resolve(
            text=user_input,
            category=task_category,
            declared=data_sensitivity,
        )

        # ── Step 3.5: Role-Filtered Knowledge Retrieval (RAG) ────────
        rag_result = self.rag_retriever.retrieve(query=user_input, auth=auth)
        rag_evidence: list[str] = []
        if rag_result.chunks:
            rag_evidence = [f"rag_doc:{c.doc_title}" for c in rag_result.chunks]
            from src.ai.schemas import _SENSITIVITY_ORDER
            from src.orchestrator.sensitivity import SensitivityResolution
            if _SENSITIVITY_ORDER[rag_result.highest_sensitivity] > _SENSITIVITY_ORDER[sensitivity.level]:
                sensitivity = SensitivityResolution(
                    level=rag_result.highest_sensitivity,
                    reasons=[
                        *sensitivity.reasons,
                        f"Elevated by organizational document clearance: {rag_result.highest_sensitivity.value}",
                    ],
                )

        # ── Step 4: Validate tool before policy/risk ─────────────────
        tool_name = tool_request.tool if tool_request else ""
        tool_permission = ""
        if tool_request:
            try:
                tool_obj = self.tool_selector.select(tool_request.tool)
                tool_permission = getattr(tool_obj, "required_permission", "")
            except ToolNotFoundError:
                await self.audit.record(
                    event_type=AuditEventType.TOOL_BLOCKED,
                    action="tool_blocked",
                    request_id=req_id,
                    user_id=auth.user_id,
                    role=auth.role,
                    decision="deny",
                    tool=tool_request.tool,
                )
                raise

        # ── Step 5: Select Agent (deterministic) ─────────────────────
        agent = self.agent_selector.select(task_category, operation_type)
        agent_name = agent.metadata.name
        agent_permission = agent.metadata.required_permission

        # ── Step 6: Build OperationContext ────────────────────────────
        # Collect extra permissions that the policy engine must check
        extra_permissions: list[str] = []
        if agent_permission and agent_permission != "ai.execute":
            extra_permissions.append(agent_permission)
        if tool_permission:
            extra_permissions.append(tool_permission)

        context = OperationContext(
            user_id=auth.user_id,
            role=auth.role,
            permission="ai.execute",
            extra_permissions=extra_permissions,
            resource=tool_name or "llm",
            action="execute",
            agent=agent_name,
            tool=tool_name,
            data_sensitivity=sensitivity.level,
            task_category=task_category,
            operation_type=operation_type,
            production_affecting=production_affecting,
            parameters=tool_request.parameters if tool_request else {},
        )

        # ── Step 7: Risk Assessment ──────────────────────────────────
        risk = self.risk_engine.assess(context)

        # ── Step 8: Policy Decision ──────────────────────────────────
        policy_result = self.policy_engine.evaluate(auth, context, risk)

        if policy_result.is_denied:
            await self.audit.record(
                event_type=AuditEventType.POLICY_DENIED,
                action="policy_denied",
                request_id=req_id,
                user_id=auth.user_id,
                role=auth.role,
                decision="deny",
                risk_level=risk.risk_level,
                resource=context.resource,
                agent=agent_name,
                metadata={
                    "reason": policy_result.reason,
                    "sensitivity": sensitivity.level.value,
                    "sensitivity_reasons": sensitivity.reasons,
                },
            )
            raise PolicyDeniedError(
                message="Operation denied by policy",
                reason=policy_result.reason,
            )

        if policy_result.requires_approval:
            approval = await self.approval_svc.create(
                request_id=req_id,
                context=context,
                risk=risk,
                operation_summary=f"AI task: {user_input[:200]}",
            )
            await self.audit.record(
                event_type=AuditEventType.APPROVAL_CREATED,
                action="approval_created",
                request_id=req_id,
                user_id=auth.user_id,
                role=auth.role,
                decision="require_approval",
                risk_level=risk.risk_level,
                resource=context.resource,
                agent=agent_name,
                metadata={"approval_id": str(approval.id)},
            )
            raise ApprovalRequiredError(
                message=f"Operation requires approval: {policy_result.reason}",
                approval_request_id=str(approval.id),
            )

        # ── Step 9: Tool execution (if requested) ────────────────────
        tool_output = ""
        tool_used = ""
        if tool_request:
            # Tool already validated in Step 4 — safe to select directly
            tool = self.tool_selector.select(tool_request.tool)

            await self.audit.record(
                event_type=AuditEventType.TOOL_REQUEST,
                action="tool_request",
                request_id=req_id,
                user_id=auth.user_id,
                role=auth.role,
                tool=tool_request.tool,
            )
            tool_result = await tool.execute(tool_request.parameters)
            tool_used = tool_request.tool
            tool_output = (
                tool_result.output if tool_result.success else f"Error: {tool_result.error}"
            )

        # ── Step 10: Model Selection ─────────────────────────────────
        model_meta = self.model_router.select_model(task_category)
        provider = self.model_router.get_provider_for_model(model_meta)

        await self.audit.record(
            event_type=AuditEventType.LLM_REQUEST,
            action="llm_request",
            request_id=req_id,
            user_id=auth.user_id,
            role=auth.role,
            model=model_meta.name,
            agent=agent_name,
            decision="allow",
            risk_level=risk.risk_level,
        )

        # ── Step 11: Agent Execution ─────────────────────────────────
        # Agent shapes the prompt, calls the provider, returns structured result
        agent_result = await agent.execute(
            AgentRequest(
                task=user_input,
                model=model_meta.name,
                category=task_category,
                tool_output=tool_output,
                rag_context=rag_result.context_text,
                structured=structured,
            ),
            provider,
        )

        if rag_evidence:
            agent_result.evidence.extend(rag_evidence)
        if rag_result.denied_chunks_count > 0:
            agent_result.warnings.append(
                f"rag_unauthorized_records_withheld:{rag_result.denied_chunks_count}"
            )

        await self.audit.record(
            event_type=AuditEventType.LLM_RESPONSE,
            action="llm_response",
            request_id=req_id,
            user_id=auth.user_id,
            role=auth.role,
            model=model_meta.name,
            agent=agent_name,
            decision="allow" if agent_result.success else "error",
            metadata={
                "latency_ms": agent_result.execution_metadata.get("latency_ms"),
                "warnings": agent_result.warnings,
            },
        )

        # ── Step 12: Verification ────────────────────────────────────
        verification = self.verifier.verify_llm_response(
            content=agent_result.output,
            success=agent_result.success,
            error="" if agent_result.success else "; ".join(agent_result.warnings),
        )

        # ── Step 13: Audit completion ────────────────────────────────
        await self.audit.record(
            event_type=AuditEventType.EXECUTION_COMPLETED,
            action="execution_completed",
            request_id=req_id,
            user_id=auth.user_id,
            role=auth.role,
            model=model_meta.name,
            agent=agent_name,
            decision="allow",
            risk_level=risk.risk_level,
            metadata={
                "verification": verification.status,
                "sensitivity": sensitivity.level.value,
                "operation_type": operation_type.value,
                "production_affecting": production_affecting,
            },
        )

        return OrchestratorResult(
            request_id=req_id,
            task_category=task_category,
            risk_level=risk.risk_level,
            policy_decision=PolicyDecision.ALLOW,
            model_used=model_meta.name,
            content=agent_result.output,
            verification_status=verification.status,
            approval_id=None,
            tool_used=tool_used,
            tool_output=tool_output,
            success=agent_result.success,
            error="" if agent_result.success else "; ".join(agent_result.warnings),
            # Enriched fields from new architecture
            agent_used=agent_name,
            operation_type=operation_type,
            data_sensitivity=sensitivity.level,
            production_affecting=production_affecting,
            evidence=agent_result.evidence,
            warnings=agent_result.warnings,
            artifacts=agent_result.artifacts,
        )
