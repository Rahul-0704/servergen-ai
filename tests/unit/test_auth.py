"""
Phase B Tests — Authentication, JWT, and Account Security.

Tests 1-7 from the test plan:
1. Successful login
2. Wrong password
3. Account lockout
4. Inactive account
5. Token validation
6. Refresh token rotation
7. Logout/revocation
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from src.models.role import Role
from src.models.user import User
from src.services.auth_service import AuthService

# ── Helpers ──────────────────────────────────────────────────────────────


async def _seed_role(db: AsyncSession, name: str = "administrator") -> Role:
    """Create a test role."""
    role = Role(id=uuid.uuid4(), name=name, description=f"Test {name} role")
    db.add(role)
    await db.flush()
    return role


async def _seed_user(
    db: AsyncSession,
    role: Role,
    username: str = "testuser",
    password: str = "Str0ng!Pass",  # noqa: S107
    is_active: bool = True,
) -> User:
    """Create a test user with a hashed password."""
    user = User(
        id=uuid.uuid4(),
        username=username,
        email=f"{username}@test.local",
        hashed_password=hash_password(password),
        full_name=f"Test {username}",
        role_id=role.id,
        is_active=is_active,
    )
    db.add(user)
    await db.flush()
    # Attach role for relationship access
    user.role = role
    return user


# ── Test 1: Successful Login ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_successful_login(db_session: AsyncSession) -> None:
    """Valid credentials return access + refresh tokens."""
    role = await _seed_role(db_session, name="admin_login_test")
    await _seed_user(db_session, role, username="login_ok", password="Correct!Pass1")

    svc = AuthService(db_session)
    result = await svc.login("login_ok", "Correct!Pass1")

    assert result.access_token
    assert result.refresh_token
    assert result.token_type == "bearer"
    assert result.expires_in > 0

    # Access token should decode correctly
    payload = decode_token(result.access_token, expected_type="access")
    assert payload["role"] == "admin_login_test"


# ── Test 2: Wrong Password ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wrong_password(db_session: AsyncSession) -> None:
    """Invalid password raises AuthenticationError."""
    from src.core.exceptions import AuthenticationError

    role = await _seed_role(db_session, name="admin_wrong_pw")
    await _seed_user(db_session, role, username="wrong_pw", password="RightPass1!")

    svc = AuthService(db_session)
    with pytest.raises(AuthenticationError):
        await svc.login("wrong_pw", "WrongPassword!")


# ── Test 3: Account Lockout ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_account_lockout(db_session: AsyncSession) -> None:
    """After MAX_LOGIN_ATTEMPTS failures, account is locked."""
    from src.core.config import get_settings
    from src.core.exceptions import AccountLockedError, AuthenticationError

    settings = get_settings()
    role = await _seed_role(db_session, name="admin_lockout")
    await _seed_user(db_session, role, username="lockout_user", password="RealPass1!")

    svc = AuthService(db_session)

    # Fail N times
    for _ in range(settings.MAX_LOGIN_ATTEMPTS):
        with pytest.raises(AuthenticationError):
            await svc.login("lockout_user", "WrongPass!")

    # Next attempt should raise AccountLockedError
    with pytest.raises((AccountLockedError, AuthenticationError)):
        await svc.login("lockout_user", "RealPass1!")


# ── Test 4: Inactive Account ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inactive_account(db_session: AsyncSession) -> None:
    """Inactive user cannot login even with correct password."""
    from src.core.exceptions import AuthenticationError

    role = await _seed_role(db_session, name="admin_inactive")
    await _seed_user(db_session, role, username="inactive_user", password="Pass1!", is_active=False)

    svc = AuthService(db_session)
    with pytest.raises(AuthenticationError):
        await svc.login("inactive_user", "Pass1!")


# ── Test 5: Token Validation ────────────────────────────────────────────


def test_access_token_validation() -> None:
    """Valid access token decodes correctly; tampered token is rejected."""
    from src.core.exceptions import InvalidTokenError

    token = create_access_token("user-123", "administrator")
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "user-123"
    assert payload["role"] == "administrator"
    assert payload["typ"] == "access"

    # Tampered token should fail
    with pytest.raises(InvalidTokenError):
        decode_token(token + "tampered", expected_type="access")

    # Wrong type should fail
    with pytest.raises(InvalidTokenError):
        decode_token(token, expected_type="refresh")


def test_refresh_token_validation() -> None:
    """Refresh token has correct type and family ID."""
    token, family_id = create_refresh_token("user-456")
    payload = decode_token(token, expected_type="refresh")
    assert payload["sub"] == "user-456"
    assert payload["typ"] == "refresh"
    assert payload["fid"] == family_id


# ── Test 6: Refresh Token Rotation ──────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_rotation(db_session: AsyncSession) -> None:
    """Refresh rotation: old token revoked, new pair issued, old token rejected on reuse."""
    from src.core.exceptions import InvalidTokenError

    role = await _seed_role(db_session, name="admin_refresh")
    await _seed_user(db_session, role, username="refresh_user", password="Pass1!")

    svc = AuthService(db_session)

    # Login to get initial tokens
    tokens1 = await svc.login("refresh_user", "Pass1!")

    # Refresh to get new tokens
    tokens2 = await svc.refresh(tokens1.refresh_token)
    assert tokens2.access_token != tokens1.access_token
    assert tokens2.refresh_token != tokens1.refresh_token

    # Old refresh token should be rejected (reuse detection)
    with pytest.raises(InvalidTokenError):
        await svc.refresh(tokens1.refresh_token)


# ── Test 7: Logout/Revocation ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_logout_revocation(db_session: AsyncSession) -> None:
    """After logout, the refresh token cannot be used."""
    from src.core.exceptions import InvalidTokenError

    role = await _seed_role(db_session, name="admin_logout")
    await _seed_user(db_session, role, username="logout_user", password="Pass1!")

    svc = AuthService(db_session)
    tokens = await svc.login("logout_user", "Pass1!")

    # Logout
    await svc.logout(tokens.refresh_token)

    # Refresh should fail after logout
    with pytest.raises(InvalidTokenError):
        await svc.refresh(tokens.refresh_token)


# ── Unit tests for password hashing ─────────────────────────────────────


def test_argon2id_hash_and_verify() -> None:
    """Argon2id hashing produces verifiable hashes; wrong password fails."""
    hashed = hash_password("MySecure!Password")
    assert hashed != "MySecure!Password"
    assert hashed.startswith("$argon2id$")
    assert verify_password("MySecure!Password", hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_token_hash() -> None:
    """Token hashing produces consistent SHA-256 hex digest."""
    h1 = hash_token("my-token")
    h2 = hash_token("my-token")
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex digest
    assert hash_token("different-token") != h1


# ── Test 8: Auth Events Audit Trail ─────────────────────────────────────


@pytest.mark.asyncio
async def test_auth_actions_recorded_in_audit(db_session: AsyncSession) -> None:
    """Login success, failure, refresh, and logout must all be recorded in the audit ledger."""
    from src.core.exceptions import AuthenticationError
    from src.repositories.audit_repository import AuditFilters
    from src.services.audit_service import AuditEventType, AuditService

    role = await _seed_role(db_session, name="audit_test_role")
    await _seed_user(db_session, role, username="audited_user", password="Pass123!Secure")

    svc = AuthService(db_session)
    audit = AuditService(db_session)

    # 1. Login Failure
    with pytest.raises(AuthenticationError):
        await svc.login("audited_user", "WrongPassword!")

    failure_events = await audit.repo.list_events(
        filters=AuditFilters(event_type=AuditEventType.LOGIN_FAILURE),
        descending=True,
    )
    assert len(failure_events) >= 1
    assert failure_events[0].decision == "deny"
    assert failure_events[0].metadata_json.get("username") == "audited_user"

    # 2. Login Success
    tokens = await svc.login("audited_user", "Pass123!Secure")
    success_events = await audit.repo.list_events(
        filters=AuditFilters(event_type=AuditEventType.LOGIN_SUCCESS),
        descending=True,
    )
    assert len(success_events) >= 1
    assert success_events[0].decision == "allow"
    assert success_events[0].user_id is not None

    # 3. Token Refresh
    tokens2 = await svc.refresh(tokens.refresh_token)
    refresh_events = await audit.repo.list_events(
        filters=AuditFilters(event_type=AuditEventType.TOKEN_REFRESH),
        descending=True,
    )
    assert len(refresh_events) >= 1
    assert refresh_events[0].decision == "allow"

    # 4. Logout
    await svc.logout(tokens2.refresh_token)
    logout_events = await audit.repo.list_events(
        filters=AuditFilters(event_type=AuditEventType.LOGOUT),
        descending=True,
    )
    assert len(logout_events) >= 1
    assert logout_events[0].decision == "allow"
