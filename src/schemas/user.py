"""
ServerGen AI — User Management Schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCreateRequest(BaseModel):
    """Payload to create a new user."""

    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=255)
    role: str = Field(default="general_employee", description="System role name")


class UserUpdateRequest(BaseModel):
    """Payload to update an existing user."""

    email: str | None = Field(default=None, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, description="System role name")
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserResponse(BaseModel):
    """User representation exposed to authorized API clients."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login: datetime | None = None
    created_at: datetime


class UserPage(BaseModel):
    """Paginated user listing."""

    items: list[UserResponse]
    total: int
    skip: int
    limit: int
