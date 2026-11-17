"""
ServerGen AI — AI Orchestrator API Routes.

GET  /api/v1/ai/models   — list registered models
GET  /api/v1/ai/agents   — list registered agents
GET  /api/v1/ai/tasks    — list task categories
POST /api/v1/ai/execute  — submit a task through the full security pipeline
"""

from __future__ import annotations

import contextlib
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.base import build_default_agent_registry
from src.ai.model_registry import build_default_registry
from src.auth.permissions import PermissionCode
from src.auth.rbac import AuthContext, get_auth_context, require_permission
from src.core.database import get_db
from src.core.exceptions import ApprovalRequiredError, PolicyDeniedError, ToolNotFoundError
from src.orchestrator.engine import OrchestratorEngine
from src.schemas.orchestrator import TaskRequest, TaskResponse, orchestrator_result_to_task_response
from src.tools.base import ToolRequest

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])

_ai_execute = require_permission(PermissionCode.AI_EXECUTE)
_ai_read = require_permission(PermissionCode.AI_READ)


@router.get("/models", dependencies=[Depends(_ai_read)])
async def list_models() -> list[dict]:
    """List all registered AI models with active local Ollama presence detection."""
    from src.ai.providers.base import ModelCapability, ModelMetadata

    registry = build_default_registry()
    provider = registry.get_provider("ollama")
    available_in_provider: set[str] = set()
    if provider and hasattr(provider, "list_models"):
        with contextlib.suppress(Exception):
            available_in_provider = set(await provider.list_models())

    # Dynamically register any installed models found in Ollama
    for installed_name in available_in_provider:
        if not registry.get_model(installed_name):
            registry.register_model(
                ModelMetadata(
                    name=installed_name,
                    provider="ollama",
                    capabilities=[
                        ModelCapability.GENERAL,
                        ModelCapability.DOCUMENT,
                        ModelCapability.REASONING,
                        ModelCapability.CODING,
                    ],
                    context_length=8192,
                    minimum_ram_gb=4.0,
                    recommended_ram_gb=8.0,
                    minimum_vram_gb=2.0,
                    recommended_vram_gb=4.0,
                    requires_gpu=False,
                    enabled=True,
                    priority=8,
                )
            )

    models_out = []
    for m in registry.list_models():
        is_inst = (m.name in available_in_provider) or any(
            m.name in a for a in available_in_provider
        )
        is_en = m.enabled and (not available_in_provider or is_inst)
        models_out.append(
            {
                "name": m.name,
                "provider": m.provider,
                "capabilities": [c.value for c in m.capabilities],
                "context_length": m.context_length,
                "requires_gpu": m.requires_gpu,
                "minimum_ram_gb": m.minimum_ram_gb,
                "minimum_vram_gb": m.minimum_vram_gb,
                "enabled": is_en,
                "installed": is_inst,
            }
        )
    return models_out


@router.get("/agents", dependencies=[Depends(_ai_read)])
async def list_agents() -> list[dict]:
    """List all registered agents."""
    reg = build_default_agent_registry()
    return [
        {
            "name": a.name,
            "capability": a.capability.value,
            "description": a.description,
            "required_permission": a.required_permission,
        }
        for a in reg.list_agents()
    ]


@router.get("/tasks", dependencies=[Depends(_ai_read)])
async def list_task_categories() -> list[str]:
    """List supported task categories."""
    from src.ai.schemas import TaskCategory

    return [c.value for c in TaskCategory]


@router.post(
    "",
    response_model=TaskResponse,
    dependencies=[Depends(_ai_execute)],
)
@router.post(
    "/execute",
    response_model=TaskResponse,
    dependencies=[Depends(_ai_execute)],
)
async def execute_task(
    body: TaskRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    """
    Submit an AI task through the full security pipeline.

    Flow: Auth → RBAC → Classification → Sensitivity → Risk → Policy
         → Agent → LLM → Verify → Audit
    """
    engine = OrchestratorEngine(db)

    tool_request = None
    if body.tool:
        tool_request = ToolRequest(
            requested_action=body.input,
            tool=body.tool,
            parameters=body.tool_parameters,
        )

    from src.core.middleware import get_request_id
    req_id = get_request_id() or str(uuid.uuid4())

    try:
        result = await engine.execute(
            auth=auth,
            user_input=body.input,
            data_sensitivity=body.data_sensitivity,
            tool_request=tool_request,
            request_id=req_id,
            structured=body.structured,
            requested_model=body.model,
            approval_id=body.approval_id,
        )
        return orchestrator_result_to_task_response(result)

    except ApprovalRequiredError as exc:
        return TaskResponse(
            request_id=req_id,
            task_category="unknown",
            risk_level="high",
            policy_decision="require_approval",
            model_used="",
            content="",
            verification_status="unverified",
            success=False,
            error=exc.message,
            approval_id=exc.approval_request_id,
        )

    except (PolicyDeniedError, ToolNotFoundError) as exc:
        return TaskResponse(
            request_id=req_id,
            task_category="unknown",
            risk_level="unknown",
            policy_decision="deny",
            model_used="",
            content="",
            verification_status="unverified",
            success=False,
            error=exc.message,
        )


orchestrator_alias_router = APIRouter(prefix="/api/v1/orchestrator", tags=["orchestrator"])
orchestrator_alias_router.add_api_route(
    "",
    execute_task,
    methods=["POST"],
    response_model=TaskResponse,
    dependencies=[Depends(_ai_execute)],
)
orchestrator_alias_router.add_api_route(
    "/",
    execute_task,
    methods=["POST"],
    response_model=TaskResponse,
    dependencies=[Depends(_ai_execute)],
)
