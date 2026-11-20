"""
ServerGen AI — Approval API Routes.

GET    /api/v1/approvals              — list approvals (scoped: mine or review)
GET    /api/v1/approvals/{id}         — get approval (visibility-scoped)
POST   /api/v1/approvals/{id}/approve — approve (requires approval.approve permission)
POST   /api/v1/approvals/{id}/reject  — reject (requires approval.approve permission)
POST   /api/v1/approvals/{id}/cancel  — cancel (requester only)
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.permissions import PermissionCode
from src.auth.rbac import AuthContext, get_auth_context, require_permission
from src.core.database import get_db
from src.schemas.approval import ApprovalActionRequest, ApprovalPage, ApprovalResponse
from src.services.approval_service import ApprovalService

logger = logging.getLogger("servergen.api.approvals")

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


def _svc(db: Annotated[AsyncSession, Depends(get_db)]) -> ApprovalService:
    return ApprovalService(db)


@router.get("", response_model=ApprovalPage)
async def list_approvals(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    svc: Annotated[ApprovalService, Depends(_svc)],
    scope: str = Query(default="mine", pattern="^(mine|review)$"),
    status: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> ApprovalPage:
    """
    List approvals.

    - **mine**: approvals the caller requested (default).
    - **review**: other users' pending requests awaiting a decision
      (requires ``approval.approve``).
    """
    items, total = await svc.list_for(auth, scope=scope, status=status, skip=skip, limit=limit)
    return ApprovalPage(
        items=[ApprovalResponse.model_validate(a) for a in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{approval_id}", response_model=ApprovalResponse)
async def get_approval(
    approval_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    svc: Annotated[ApprovalService, Depends(_svc)],
) -> ApprovalResponse:
    """Get an approval request by ID (scoped visibility)."""
    approval = await svc.get_visible(approval_id, auth)
    return ApprovalResponse.model_validate(approval)


@router.post(
    "/{approval_id}/approve",
    response_model=ApprovalResponse,
    dependencies=[Depends(require_permission(PermissionCode.APPROVAL_APPROVE))],
)
async def approve(
    approval_id: uuid.UUID,
    body: ApprovalActionRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    svc: Annotated[ApprovalService, Depends(_svc)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApprovalResponse:
    """Approve a pending operation. Requires approval.approve permission."""
    approval = await svc.approve(
        approval_id,
        reviewer_user_id=auth.user_id,
        reviewer_role=auth.role,
        notes=body.notes,
    )

    exec_result_dict = None
    if approval.operation_payload and isinstance(approval.operation_payload, dict):
        try:
            from src.ai.schemas import DataSensitivity
            from src.auth.rbac import resolve_permissions
            from src.orchestrator.engine import OrchestratorEngine
            from src.schemas.orchestrator import orchestrator_result_to_task_response
            from src.tools.base import ToolRequest

            engine = OrchestratorEngine(db)
            tool_req = None
            if approval.operation_payload.get("tool"):
                tool_req = ToolRequest(
                    requested_action=approval.operation_payload.get("input", approval.operation_summary),
                    tool=approval.operation_payload["tool"],
                    parameters=approval.operation_payload.get("tool_parameters", {}),
                )

            # Resume execution under original requester's operational context
            req_auth = AuthContext(
                user_id=str(approval.requester_user_id),
                role=approval.requester_role,
                permissions=resolve_permissions(approval.requester_role),
            )

            res = await engine.execute(
                auth=req_auth,
                user_input=approval.operation_payload.get("input", ""),
                data_sensitivity=DataSensitivity(approval.operation_payload.get("data_sensitivity", "internal")),
                tool_request=tool_req,
                structured=approval.operation_payload.get("structured", False),
                requested_model=approval.operation_payload.get("model"),
                approval_id=str(approval.id),
            )
            task_resp = orchestrator_result_to_task_response(res)
            exec_result_dict = task_resp.model_dump()

            # Enforce single-use: mark approval as consumed
            try:
                await svc.consume(approval)
            except Exception as cons_err:
                logger.debug("Approval consume notice: %s", cons_err)
        except Exception as e:
            exec_result_dict = {"success": False, "error": str(e)}

    resp = ApprovalResponse.model_validate(approval)
    resp.execution_result = exec_result_dict
    return resp


@router.post(
    "/{approval_id}/reject",
    response_model=ApprovalResponse,
    dependencies=[Depends(require_permission(PermissionCode.APPROVAL_APPROVE))],
)
async def reject(
    approval_id: uuid.UUID,
    body: ApprovalActionRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    svc: Annotated[ApprovalService, Depends(_svc)],
) -> ApprovalResponse:
    """Reject a pending approval request. Requires approval.approve permission."""
    approval = await svc.reject(
        approval_id,
        reviewer_user_id=auth.user_id,
        reviewer_role=auth.role,
        notes=body.notes,
    )
    return ApprovalResponse.model_validate(approval)


@router.post("/{approval_id}/cancel", response_model=ApprovalResponse)
async def cancel(
    approval_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    svc: Annotated[ApprovalService, Depends(_svc)],
) -> ApprovalResponse:
    """Cancel a pending approval (original requester only)."""
    approval = await svc.cancel(
        approval_id,
        requester_user_id=auth.user_id,
        requester_role=auth.role,
    )
    return ApprovalResponse.model_validate(approval)
