"""
ServerGen AI — Authentication Pydantic Schemas.

Request/response models for auth endpoints. Passwords are never included
in response schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

# ── Requests ─────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    """Login credentials. Password max length prevents hash DoS."""

    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=128)


class RegisterRequest(BaseModel):
    """User self-registration request."""

    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_\-]+$")
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=255)


class RefreshRequest(BaseModel):
    """Refresh token submission for rotation."""

    refresh_token: str = Field(..., min_length=1)


class LogoutRequest(BaseModel):
    """Refresh token to revoke on logout."""

    refresh_token: str = Field(..., min_length=1)


# ── Responses ────────────────────────────────────────────────────────────


class TokenResponse(BaseModel):
    """Access + refresh token pair. Returned on login and refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


class UserProfile(BaseModel):
    """Current user profile. Never includes password hash."""

    id: uuid.UUID
    username: str
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthError(BaseModel):
    """Standard auth error response."""

    error: str
    message: str
    request_id: str
