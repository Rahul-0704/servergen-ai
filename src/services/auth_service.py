"""
ServerGen AI — Authentication Service.

Business logic for login, refresh token rotation, logout, and account lockout.
All security decisions are made here — never in the API layer.
Every authentication event is recorded in the tamper-evident audit ledger.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.permissions import SystemRole
from src.core.config import get_settings
from src.core.exceptions import (
    AccountLockedError,
    AuthenticationError,
    ConflictError,
    InvalidTokenError,
    ValidationError,
)
from src.core.middleware import get_request_id
from src.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
    verify_password_dummy,
)
from src.models.session import RefreshSession
from src.models.user import User
from src.repositories.role_repository import RoleRepository
from src.repositories.session_repository import SessionRepository
from src.repositories.user_repository import UserRepository
from src.schemas import TokenResponse, UserProfile
from src.services.audit_service import AuditEventType, AuditService


class AuthService:
    """Authentication service handling login, refresh, logout, lockout, and audit recording."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.session_repo = SessionRepository(db)
        self.audit = AuditService(db)
        self.settings = get_settings()

    async def register(
        self,
        username: str,
        email: str,
        password: str,
        full_name: str = "",
        user_agent: str | None = None,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> TokenResponse:
        """
        Self-register a new user account with default general_employee role.
        Issues access and refresh tokens immediately upon registration.
        """
        req_id = request_id or get_request_id() or str(uuid.uuid4())

        # 1. Uniqueness check
        if await self.user_repo.get_by_username(username):
            raise ConflictError(f"Username '{username}' is already taken")
        if await self.user_repo.get_by_email(email):
            raise ConflictError(f"Email '{email}' is already registered")

        # 2. Password length validation
        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters")

        # 3. Retrieve default role
        role_repo = RoleRepository(self.db)
        role = await role_repo.get_by_name(SystemRole.GENERAL_EMPLOYEE.value)
        if role is None:
            role = await role_repo.get_by_name("general_employee")
            if role is None:
                raise ValidationError("Default user role 'general_employee' is not configured")

        # 4. Create user
        now = datetime.now(UTC)
        user = User(
            id=uuid.uuid4(),
            username=username,
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name or username,
            role_id=role.id,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        await self.user_repo.create(user)
        user.role = role

        # 5. Issue token pair with family tracking
        role_name = role.name
        access_token = create_access_token(str(user.id), role_name)
        refresh_token, family_id = create_refresh_token(str(user.id))

        session = RefreshSession(
            user_id=user.id,
            refresh_token_hash=hash_token(refresh_token),
            family_id=family_id,
            issued_at=now,
            expires_at=now + timedelta(minutes=self.settings.REFRESH_TOKEN_EXPIRE_MINUTES),
            user_agent=user_agent,
            ip_address=ip_address,
        )
        await self.session_repo.create(session)

        # 6. Audit recording
        await self.audit.record(
            event_type=AuditEventType.LOGIN_SUCCESS,
            action="user_registered",
            request_id=req_id,
            decision="allow",
            risk_level="low",
            user_id=str(user.id),
            role=role_name,
            resource="auth:register",
            metadata={"username": username, "email": email, "ip_address": ip_address, "user_agent": user_agent},
        )
        await self.db.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def login(
        self,
        username: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> TokenResponse:
        """
        Authenticate user and return token pair.

        Implements:
        - Timing-safe user lookup (dummy hash on not-found)
        - Account lockout after N failures
        - Failed login tracking
        - Refresh token stored as hash
        - Audit trail for success and all failure modes
        """
        req_id = request_id or get_request_id() or str(uuid.uuid4())
        user = await self.user_repo.get_by_username(username)

        if user is None:
            # Timing attack mitigation: execute dummy verification
            verify_password_dummy()
            await self.audit.record(
                event_type=AuditEventType.LOGIN_FAILURE,
                action="login_failure",
                request_id=req_id,
                decision="deny",
                risk_level="low",
                resource="auth:login",
                metadata={
                    "username": username,
                    "reason": "user_not_found",
                    "ip_address": ip_address,
                },
            )
            await self.db.commit()
            raise AuthenticationError("Invalid credentials")

        # Check account lockout (normalize tz for SQLite/Postgres compat)
        if user.locked_until:
            lock_ts = user.locked_until
            if lock_ts.tzinfo is None:
                lock_ts = lock_ts.replace(tzinfo=UTC)
            if lock_ts > datetime.now(UTC):
                await self.audit.record(
                    event_type=AuditEventType.LOGIN_FAILURE,
                    action="login_failure",
                    request_id=req_id,
                    decision="deny",
                    risk_level="medium",
                    user_id=str(user.id),
                    role=user.role.name if user.role else None,
                    resource="auth:login",
                    metadata={
                        "username": username,
                        "reason": "account_locked",
                        "locked_until": lock_ts.isoformat(),
                        "ip_address": ip_address,
                    },
                )
                await self.db.commit()
                raise AccountLockedError()

        # Check if account is active
        if not user.is_active:
            await self.audit.record(
                event_type=AuditEventType.LOGIN_FAILURE,
                action="login_failure",
                request_id=req_id,
                decision="deny",
                risk_level="medium",
                user_id=str(user.id),
                role=user.role.name if user.role else None,
                resource="auth:login",
                metadata={
                    "username": username,
                    "reason": "account_inactive",
                    "ip_address": ip_address,
                },
            )
            await self.db.commit()
            raise AuthenticationError("Account is inactive")

        # Verify password
        if not verify_password(password, user.hashed_password):
            await self._handle_failed_login(user)
            await self.audit.record(
                event_type=AuditEventType.LOGIN_FAILURE,
                action="login_failure",
                request_id=req_id,
                decision="deny",
                risk_level="medium" if user.locked_until else "low",
                user_id=str(user.id),
                role=user.role.name if user.role else None,
                resource="auth:login",
                metadata={
                    "username": username,
                    "reason": "invalid_password",
                    "failed_attempts": user.failed_login_attempts,
                    "locked": bool(user.locked_until),
                    "ip_address": ip_address,
                },
            )
            await self.db.commit()  # Persist failed login tracking and audit before raising
            raise AuthenticationError("Invalid credentials")

        # Success — reset failed attempts and update last login
        await self.user_repo.reset_failed_logins(user.id)
        await self.user_repo.update_last_login(user.id)

        # Create token pair
        role_name = user.role.name if user.role else "unknown"
        access_token = create_access_token(str(user.id), role_name)
        refresh_token, family_id = create_refresh_token(str(user.id))

        # Store refresh session (hashed token, not plaintext)
        now = datetime.now(UTC)
        session = RefreshSession(
            user_id=user.id,
            refresh_token_hash=hash_token(refresh_token),
            family_id=family_id,
            issued_at=now,
            expires_at=now + timedelta(minutes=self.settings.REFRESH_TOKEN_EXPIRE_MINUTES),
            user_agent=user_agent,
            ip_address=ip_address,
        )
        await self.session_repo.create(session)

        # Record login success in audit ledger
        await self.audit.record(
            event_type=AuditEventType.LOGIN_SUCCESS,
            action="login_success",
            request_id=req_id,
            decision="allow",
            risk_level="low",
            user_id=str(user.id),
            role=role_name,
            resource="auth:login",
            metadata={"username": username, "ip_address": ip_address, "user_agent": user_agent},
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def refresh(self, refresh_token_str: str, request_id: str | None = None) -> TokenResponse:
        """
        Rotate refresh token — invalidate old, issue new pair.

        If a revoked token is reused, the entire token family is invalidated
        (breach detection). Every refresh is audited.
        """
        req_id = request_id or get_request_id() or str(uuid.uuid4())

        # Decode and validate the refresh token
        try:
            decode_token(refresh_token_str, expected_type="refresh")
        except Exception as exc:
            raise InvalidTokenError("Invalid refresh token") from exc

        # Look up the stored session by token hash
        token_hash = hash_token(refresh_token_str)
        session = await self.session_repo.get_by_token_hash(token_hash)

        if session is None:
            raise InvalidTokenError("Refresh token not found")

        # If this token was already revoked → reuse detected → revoke entire family
        if session.revoked:
            await self.session_repo.revoke_family(session.family_id)
            await self.audit.record(
                event_type=AuditEventType.LOGIN_FAILURE,
                action="token_reuse_detected",
                request_id=req_id,
                decision="deny",
                risk_level="high",
                user_id=str(session.user_id),
                resource="auth:refresh",
                metadata={"family_id": session.family_id, "warning": "revoked_token_reused"},
            )
            await self.db.commit()
            raise InvalidTokenError("Refresh token reuse detected — family revoked")

        # Check expiration (handle both timezone-aware and naive datetimes from different DBs)
        expires_at = session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < datetime.now(UTC):
            raise InvalidTokenError("Refresh token expired")

        # Get user
        user = await self.user_repo.get_by_id(session.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("User not found or inactive")

        # Rotate: revoke old session, create new pair
        role_name = user.role.name if user.role else "unknown"
        new_access = create_access_token(str(user.id), role_name)
        new_refresh, _ = create_refresh_token(str(user.id), family_id=session.family_id)

        now = datetime.now(UTC)
        new_session = RefreshSession(
            user_id=user.id,
            refresh_token_hash=hash_token(new_refresh),
            family_id=session.family_id,
            issued_at=now,
            expires_at=now + timedelta(minutes=self.settings.REFRESH_TOKEN_EXPIRE_MINUTES),
        )
        await self.session_repo.create(new_session)

        # Revoke the old session, linking to the new one
        await self.session_repo.revoke(session.id, replaced_by=new_session.id)

        # Record token refresh in audit ledger
        await self.audit.record(
            event_type=AuditEventType.TOKEN_REFRESH,
            action="token_refresh",
            request_id=req_id,
            decision="allow",
            risk_level="low",
            user_id=str(user.id),
            role=role_name,
            resource="auth:refresh",
            metadata={"family_id": session.family_id},
        )

        return TokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            expires_in=self.settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def logout(self, refresh_token_str: str, request_id: str | None = None) -> None:
        """Revoke a refresh token on logout and record in audit ledger."""
        req_id = request_id or get_request_id() or str(uuid.uuid4())
        token_hash = hash_token(refresh_token_str)
        session = await self.session_repo.get_by_token_hash(token_hash)
        if session and not session.revoked:
            await self.session_repo.revoke(session.id)
            await self.audit.record(
                event_type=AuditEventType.LOGOUT,
                action="logout",
                request_id=req_id,
                decision="allow",
                risk_level="low",
                user_id=str(session.user_id),
                resource="auth:logout",
                metadata={"session_id": str(session.id)},
            )

    async def get_profile(self, user_id: str) -> UserProfile:
        """Get user profile by ID."""
        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if user is None:
            raise AuthenticationError("User not found")
        return UserProfile(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            role=user.role.name if user.role else "unknown",
            is_active=user.is_active,
            last_login=user.last_login,
            created_at=user.created_at,
        )

    async def _handle_failed_login(self, user: User) -> None:
        """Track failed login and lock account if threshold exceeded."""
        await self.user_repo.increment_failed_logins(user.id)
        # Refresh from DB to get actual count (in-memory object is stale)
        await self.db.refresh(user)

        if user.failed_login_attempts >= self.settings.MAX_LOGIN_ATTEMPTS:
            lock_until = datetime.now(UTC) + timedelta(
                minutes=self.settings.LOCKOUT_DURATION_MINUTES
            )
            await self.user_repo.lock_account(user.id, lock_until)
