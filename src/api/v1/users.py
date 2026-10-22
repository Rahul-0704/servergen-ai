"""
ServerGen AI — User Management API Routes.

GET    /api/v1/users              — list users (requires user.read)
GET    /api/v1/users/{id}         — get user details (requires user.read)
POST   /api/v1/users              — create user (requires user.write)
PATCH  /api/v1/users/{id}         — update user (requires user.write)
POST   /api/v1/users/{id}/disable — disable user & revoke sessions (requires user.write)
POST   /api/v1/users/{id}/enable  — re-enable user (requires user.write)
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.permissions import PermissionCode
from src.auth.rbac import AuthContext, get_auth_context, require_permission
from src.core.database import get_db
from src.schemas.user import UserCreateRequest, UserPage, UserResponse, UserUpdateRequest
from src.services.user_service import UserService

router = APIRouter(prefix="/api/v1/users", tags=["users"])

_user_read = require_permission(PermissionCode.USER_READ)
_user_write = require_permission(PermissionCode.USER_WRITE)


def _svc(db: Annotated[AsyncSession, Depends(get_db)]) -> UserService:
    return UserService(db)


def _user_to_response(user) -> UserResponse:
    role_name = user.role.name if user.role else "unknown"
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=role_name,
        is_active=user.is_active,
        last_login=user.last_login,
        created_at=user.created_at,
    )


@router.get("", response_model=UserPage, dependencies=[Depends(_user_read)])
async def list_users(
    svc: Annotated[UserService, Depends(_svc)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    active_only: bool = Query(default=False),
    role: str | None = Query(default=None),
) -> UserPage:
    """List users with optional role and status filters."""
    users, total = await svc.list_users(
        skip=skip, limit=limit, active_only=active_only, role_name=role
    )
    return UserPage(
        items=[_user_to_response(u) for u in users],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/me", response_model=UserResponse)
async def get_my_user(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    svc: Annotated[UserService, Depends(_svc)],
) -> UserResponse:
    """Get current authenticated user profile."""
    user = await svc.get_user(uuid.UUID(auth.user_id))
    return _user_to_response(user)


@router.get("/{user_id}", response_model=UserResponse, dependencies=[Depends(_user_read)])
async def get_user(
    user_id: uuid.UUID,
    svc: Annotated[UserService, Depends(_svc)],
) -> UserResponse:
    """Get single user details by ID."""
    user = await svc.get_user(user_id)
    return _user_to_response(user)


@router.post("", response_model=UserResponse, dependencies=[Depends(_user_write)])
async def create_user(
    body: UserCreateRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    svc: Annotated[UserService, Depends(_svc)],
) -> UserResponse:
    """Create a new user account (admin only)."""
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    user = await svc.create_user(
        body, actor_id=auth.user_id, actor_role=auth.role, request_id=req_id
    )
    return _user_to_response(user)


@router.patch("/{user_id}", response_model=UserResponse, dependencies=[Depends(_user_write)])
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdateRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    svc: Annotated[UserService, Depends(_svc)],
) -> UserResponse:
    """Update user information (admin only)."""
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    user = await svc.update_user(
        user_id, body, actor_id=auth.user_id, actor_role=auth.role, request_id=req_id
    )
    return _user_to_response(user)


@router.post("/{user_id}/disable", response_model=UserResponse, dependencies=[Depends(_user_write)])
async def disable_user(
    user_id: uuid.UUID,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    svc: Annotated[UserService, Depends(_svc)],
) -> UserResponse:
    """Disable user account and revoke all sessions immediately (admin only)."""
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    user = await svc.disable_user(
        user_id, actor_id=auth.user_id, actor_role=auth.role, request_id=req_id
    )
    return _user_to_response(user)


@router.post("/{user_id}/enable", response_model=UserResponse, dependencies=[Depends(_user_write)])
async def enable_user(
    user_id: uuid.UUID,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    svc: Annotated[UserService, Depends(_svc)],
) -> UserResponse:
    """Re-enable a disabled user account (admin only)."""
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    user = await svc.enable_user(
        user_id, actor_id=auth.user_id, actor_role=auth.role, request_id=req_id
    )
    return _user_to_response(user)
