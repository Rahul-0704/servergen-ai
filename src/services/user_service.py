"""
ServerGen AI — User Management Service.

Business logic for user provisioning, updates, activation/deactivation,
and full tamper-evident audit ledger tracking.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, NotFoundError, ValidationError
from src.core.security import hash_password
from src.models.user import User
from src.repositories.role_repository import RoleRepository
from src.repositories.session_repository import SessionRepository
from src.repositories.user_repository import UserRepository
from src.schemas.user import UserCreateRequest, UserUpdateRequest
from src.services.audit_service import AuditEventType, AuditService


class UserService:
    """Service handling user administration operations with audit logging."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.role_repo = RoleRepository(db)
        self.session_repo = SessionRepository(db)
        self.audit = AuditService(db)

    async def get_user(self, user_id: uuid.UUID) -> User:
        """Fetch user by ID or raise NotFoundError."""
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")
        return user

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 50,
        active_only: bool = False,
        role_name: str | None = None,
    ) -> tuple[list[User], int]:
        """List users with optional role and status filters, and pagination."""
        role_id: uuid.UUID | None = None
        if role_name:
            role = await self.role_repo.get_by_name(role_name)
            if role is None:
                return [], 0
            role_id = role.id

        users = await self.user_repo.list_users(
            skip=skip, limit=limit, active_only=active_only, role_id=role_id
        )
        total = await self.user_repo.count_users(active_only=active_only, role_id=role_id)
        return users, total

    async def create_user(
        self,
        body: UserCreateRequest,
        actor_id: str,
        actor_role: str,
        request_id: str,
    ) -> User:
        """Create a new user account, hash password, assign role, and audit."""
        # 1. Check uniqueness
        if await self.user_repo.get_by_username(body.username):
            raise ConflictError(f"Username '{body.username}' is already taken")
        if await self.user_repo.get_by_email(body.email):
            raise ConflictError(f"Email '{body.email}' is already registered")

        # 2. Check role existence
        role = await self.role_repo.get_by_name(body.role)
        if role is None:
            raise ValidationError(f"Role '{body.role}' does not exist")

        # 3. Create user
        now = datetime.now(UTC)
        user = User(
            id=uuid.uuid4(),
            username=body.username,
            email=body.email,
            hashed_password=hash_password(body.password),
            full_name=body.full_name,
            role_id=role.id,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        created = await self.user_repo.create(user)
        # Attach role object for serialization
        created.role = role

        # 4. Audit ledger entry
        await self.audit.record(
            event_type=AuditEventType.USER_CREATED,
            action="user_created",
            request_id=request_id,
            decision="allow",
            risk_level="medium",
            user_id=actor_id,
            role=actor_role,
            resource=f"user:{created.id}",
            metadata={"username": created.username, "role": role.name, "email": created.email},
        )

        return created

    async def update_user(
        self,
        user_id: uuid.UUID,
        body: UserUpdateRequest,
        actor_id: str,
        actor_role: str,
        request_id: str,
    ) -> User:
        """Update user properties (email, full_name, role, password) and audit."""
        user = await self.get_user(user_id)
        changes: dict[str, str] = {}

        if body.email and body.email != user.email:
            existing = await self.user_repo.get_by_email(body.email)
            if existing and existing.id != user.id:
                raise ConflictError(f"Email '{body.email}' is already in use")
            user.email = body.email
            changes["email"] = body.email

        if body.full_name is not None and body.full_name != user.full_name:
            user.full_name = body.full_name
            changes["full_name"] = body.full_name

        if body.role and (not user.role or body.role != user.role.name):
            new_role = await self.role_repo.get_by_name(body.role)
            if new_role is None:
                raise ValidationError(f"Role '{body.role}' does not exist")
            user.role_id = new_role.id
            user.role = new_role
            changes["role"] = new_role.name

        if body.password:
            user.hashed_password = hash_password(body.password)
            changes["password"] = "[REACHED_AND_HASHED]"
            # Revoke all current refresh sessions on password change
            await self.session_repo.revoke_all_user_sessions(user.id)

        if changes:
            user.updated_at = datetime.now(UTC)
            await self.db.flush()

            await self.audit.record(
                event_type=AuditEventType.USER_UPDATED,
                action="user_updated",
                request_id=request_id,
                decision="allow",
                risk_level="medium",
                user_id=actor_id,
                role=actor_role,
                resource=f"user:{user.id}",
                metadata={"username": user.username, "fields_changed": list(changes.keys())},
            )

        return user

    async def disable_user(
        self,
        user_id: uuid.UUID,
        actor_id: str,
        actor_role: str,
        request_id: str,
    ) -> User:
        """Disable user account and revoke all active sessions."""
        user = await self.get_user(user_id)
        if not user.is_active:
            return user

        user.is_active = False
        user.updated_at = datetime.now(UTC)
        await self.db.flush()
        # Revoke all sessions for immediate session termination
        await self.session_repo.revoke_all_user_sessions(user.id)

        await self.audit.record(
            event_type=AuditEventType.USER_DISABLED,
            action="user_disabled",
            request_id=request_id,
            decision="allow",
            risk_level="high",
            user_id=actor_id,
            role=actor_role,
            resource=f"user:{user.id}",
            metadata={"username": user.username},
        )
        return user

    async def enable_user(
        self,
        user_id: uuid.UUID,
        actor_id: str,
        actor_role: str,
        request_id: str,
    ) -> User:
        """Re-enable a disabled user account."""
        user = await self.get_user(user_id)
        if user.is_active:
            return user

        user.is_active = True
        user.updated_at = datetime.now(UTC)
        await self.db.flush()

        await self.audit.record(
            event_type=AuditEventType.USER_ENABLED,
            action="user_enabled",
            request_id=request_id,
            decision="allow",
            risk_level="medium",
            user_id=actor_id,
            role=actor_role,
            resource=f"user:{user.id}",
            metadata={"username": user.username},
        )
        return user
