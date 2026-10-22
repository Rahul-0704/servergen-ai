"""
ServerGen AI — Security Utilities.

Argon2id password hashing and JWT token management.
- Passwords: Argon2id with OWASP-recommended parameters
- JWT: Fixed HS256 algorithm, never read algorithm from header
- Tokens: Separate access/refresh types with full claim validation
"""

from __future__ import annotations

import contextlib
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type

from src.core.config import get_settings

# ── Argon2id Password Hashing (OWASP 2024+ recommendations) ─────────────

_ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

# Dummy hash for timing-attack mitigation (user enumeration prevention)
_DUMMY_HASH = _ph.hash("dummy-password-for-timing-attack-mitigation")


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id. Never stores plaintext."""
    return _ph.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verify a password against its Argon2id hash.

    Returns True if valid, False otherwise. Never raises on mismatch.
    """
    try:
        return _ph.verify(hashed_password, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def verify_password_dummy() -> None:
    """
    Execute a dummy hash verification to prevent timing-based user enumeration.

    Call this when the username is not found, so the response time
    is indistinguishable from a real password check.
    """
    with contextlib.suppress(VerifyMismatchError, VerificationError, InvalidHashError):
        _ph.verify(_DUMMY_HASH, "wrong-password")


def check_needs_rehash(hashed_password: str) -> bool:
    """Check if a hash needs re-computation due to parameter changes."""
    return _ph.check_needs_rehash(hashed_password)


# ── JWT Token Management ────────────────────────────────────────────────


def create_access_token(user_id: str | uuid.UUID, role: str) -> str:
    """
    Create a short-lived JWT access token.

    Contains: sub (user_id), role, typ=access, iss, aud, jti, iat, exp.
    Does NOT contain sensitive data (passwords, permissions list, etc.).
    """
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "typ": "access",
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(user_id: str | uuid.UUID, family_id: str | None = None) -> tuple[str, str]:
    """
    Create a refresh token with family tracking for rotation reuse detection.

    Returns: (token_string, family_id)
    """
    settings = get_settings()
    now = datetime.now(UTC)
    fam_id = family_id or str(uuid.uuid4())
    payload = {
        "sub": str(user_id),
        "typ": "refresh",
        "fid": fam_id,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES),
    }
    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )
    return token, fam_id


def decode_token(token: str, expected_type: str = "access") -> dict:
    """
    Decode and validate a JWT token.

    Validates: signature, algorithm (fixed), expiration, issuer, audience, token type.
    NEVER reads algorithm from the token header — uses fixed configured algorithm.

    Raises:
        InvalidTokenError: If token is invalid, tampered, or wrong type
        TokenExpiredError: If token has expired
    """
    from src.core.exceptions import InvalidTokenError, TokenExpiredError

    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithms=[settings.JWT_ALGORITHM],  # Fixed — never from header
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
            leeway=10,  # 10s clock skew tolerance
            options={"require": ["exp", "iss", "aud", "sub", "jti", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError() from exc
    except jwt.PyJWTError as exc:
        raise InvalidTokenError() from exc

    if payload.get("typ") != expected_type:
        raise InvalidTokenError(f"Expected token type '{expected_type}'")

    return payload


def hash_token(token: str) -> str:
    """Hash a token using SHA-256 for secure storage. Never store raw tokens."""
    return hashlib.sha256(token.encode()).hexdigest()
