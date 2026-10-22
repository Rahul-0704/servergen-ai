"""
ServerGen AI — Authentication API Routes.

POST /api/v1/auth/login   — authenticate, return tokens
POST /api/v1/auth/refresh — rotate refresh token
POST /api/v1/auth/logout  — revoke refresh token
GET  /api/v1/auth/me      — current user profile
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import decode_token
from src.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserProfile,
)
from src.services.auth_service import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

security_scheme = HTTPBearer(auto_error=True)


def _get_auth_service(db: Annotated[AsyncSession, Depends(get_db)]) -> AuthService:
    return AuthService(db)


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    body: RegisterRequest,
    request: Request,
    auth_svc: Annotated[AuthService, Depends(_get_auth_service)],
) -> TokenResponse:
    """Register a new user account with default role, receive access + refresh tokens."""
    return await auth_svc.register(
        username=body.username,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    auth_svc: Annotated[AuthService, Depends(_get_auth_service)],
) -> TokenResponse:
    """Authenticate with username/password, receive access + refresh tokens."""
    return await auth_svc.login(
        username=body.username,
        password=body.password,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    auth_svc: Annotated[AuthService, Depends(_get_auth_service)],
) -> TokenResponse:
    """Rotate refresh token — old token is revoked, new pair is issued."""
    return await auth_svc.refresh(body.refresh_token)


@router.post("/logout", status_code=204)
async def logout(
    body: LogoutRequest,
    auth_svc: Annotated[AuthService, Depends(_get_auth_service)],
) -> None:
    """Revoke a refresh token. Returns 204 even if token was already revoked."""
    await auth_svc.logout(body.refresh_token)


@router.get("/me", response_model=UserProfile)
async def me(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_scheme)],
    auth_svc: Annotated[AuthService, Depends(_get_auth_service)],
) -> UserProfile:
    """Get the current authenticated user's profile."""
    payload = decode_token(credentials.credentials, expected_type="access")
    return await auth_svc.get_profile(payload["sub"])
