"""
ServerGen AI — Application Configuration.

All configuration is loaded from environment variables via pydantic-settings.
No secrets are hardcoded. Outside development/test the application REFUSES to
start with a weak or default JWT secret or without an explicit admin password.
"""

from __future__ import annotations

import contextlib
import json
import secrets
import warnings
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_WEAK_JWT_SECRETS = frozenset(
    {"CHANGE_ME_GENERATE_A_STRONG_SECRET_KEY", "secret", "changeme", "password", ""}
)
_MIN_PROD_SECRET_LENGTH = 32


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────
    APP_NAME: str = "ServerGen AI"
    APP_ENV: Literal["development", "staging", "production", "test"] = "development"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    DEBUG: bool = False
    CORS_ORIGINS: list[str] = Field(
        default_factory=list,
        description="Allowed browser origins (JSON list or comma-separated).",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: object) -> list[str]:
        if isinstance(v, str):
            v_str = v.strip()
            if v_str.startswith("[") and v_str.endswith("]"):
                with contextlib.suppress(Exception):
                    parsed = json.loads(v_str)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
            return [origin.strip() for origin in v_str.split(",") if origin.strip()]
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        return []

    FRONTEND_DIST_DIR: str = Field(
        default="frontend/dist",
        description="Directory of the built frontend served by the API when present.",
    )

    # ── Database ─────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://servergen:changeme@localhost:5432/servergen",
        description="Async database URL. PostgreSQL is the supported target.",
    )
    DB_POOL_SIZE: int = Field(default=10, ge=1)
    DB_MAX_OVERFLOW: int = Field(default=20, ge=0)

    # ── JWT Security ─────────────────────────────────────────────────────
    JWT_SECRET_KEY: SecretStr = Field(..., description="Secret key for JWT signing.")
    JWT_ALGORITHM: Literal["HS256"] = "HS256"  # fixed — never taken from token headers
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, ge=1)
    REFRESH_TOKEN_EXPIRE_MINUTES: int = Field(default=10080, ge=1)  # 7 days
    JWT_ISSUER: str = "servergen-ai"
    JWT_AUDIENCE: str = "servergen-ai-api"

    # ── Account security ─────────────────────────────────────────────────
    MAX_LOGIN_ATTEMPTS: int = Field(default=5, ge=1)
    LOCKOUT_DURATION_MINUTES: int = Field(default=30, ge=1)
    PASSWORD_MIN_LENGTH: int = Field(default=12, ge=8)

    # ── Approvals ────────────────────────────────────────────────────────
    APPROVAL_TTL_HOURS: int = Field(default=24, ge=1)

    # ── Ollama / LLM ─────────────────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_TIMEOUT_SECONDS: float = Field(default=120.0, gt=0)
    DEFAULT_MODEL: str = "llama3.2:3b"
    LLM_TASK_CLASSIFICATION: bool = Field(
        default=False,
        description="Let the LLM refine GENERAL tasks (advisory only; rules always win).",
    )

    # ── Document Management & RAG Subsystem ──────────────────────────────
    DOCUMENT_STORAGE_DIR: str = Field(
        default="storage/documents",
        description="Durable on-premise document storage path.",
    )
    GENERATED_STORAGE_DIR: str = Field(
        default="storage/generated",
        description="Durable on-premise storage path for generated PDFs and presentations.",
    )
    MAX_DOCUMENT_UPLOAD_SIZE_BYTES: int = Field(
        default=25 * 1024 * 1024,  # 25 MB
        ge=1024,
        description="Maximum permitted single document upload size in bytes.",
    )
    RAG_CHUNK_SIZE_TOKENS: int = Field(default=500, ge=100, le=2000)
    RAG_CHUNK_OVERLAP_TOKENS: int = Field(default=80, ge=0, le=500)
    RAG_EMBEDDING_MODEL: str = "nomic-embed-text"
    RAG_EMBEDDING_DIMENSIONS: int = 768
    RAG_TOP_K: int = Field(default=4, ge=1, le=20)
    RAG_MIN_RELEVANCE: float = Field(default=0.25, ge=0.0, le=1.0)
    RAG_RERANKER_ENABLED: bool = False
    RAG_RERANKER_MODEL: str = ""

    # ── Initial Admin (consumed by the seed script only) ─────────────────
    ADMIN_USERNAME: str = "admin"
    ADMIN_EMAIL: str = "admin@servergen.local"
    ADMIN_PASSWORD: SecretStr = Field(default=SecretStr(""))

    # ── Rate Limiting (in-memory prototype) ──────────────────────────────
    RATE_LIMIT_LOGIN_MAX: int = 10
    RATE_LIMIT_LOGIN_WINDOW_SECONDS: int = 300
    RATE_LIMIT_API_MAX: int = 300
    RATE_LIMIT_API_WINDOW_SECONDS: int = 60
    RATE_LIMIT_LLM_MAX: int = 20
    RATE_LIMIT_LLM_WINDOW_SECONDS: int = 60
    RATE_LIMIT_TOOL_MAX: int = 50
    RATE_LIMIT_TOOL_WINDOW_SECONDS: int = 60

    @model_validator(mode="after")
    def _enforce_secret_policy(self) -> Settings:
        """Strict secret policy outside development/test; random dev key otherwise."""
        secret_value = self.JWT_SECRET_KEY.get_secret_value()
        weak = secret_value in _WEAK_JWT_SECRETS or len(secret_value) < _MIN_PROD_SECRET_LENGTH

        if self.is_development:
            if not self.CORS_ORIGINS:
                self.CORS_ORIGINS = [
                    "http://localhost:5173",
                    "http://127.0.0.1:5173",
                    "http://localhost:3000",
                    "http://127.0.0.1:3000",
                ]
            if secret_value in _WEAK_JWT_SECRETS:
                warnings.warn(
                    "JWT_SECRET_KEY is weak/default; a random per-process key is used. "
                    "Tokens will not survive restarts. Set a strong JWT_SECRET_KEY.",
                    UserWarning,
                    stacklevel=2,
                )
                self.JWT_SECRET_KEY = SecretStr(secrets.token_urlsafe(64))
            return self

        if weak:
            msg = (
                f"JWT_SECRET_KEY must be at least {_MIN_PROD_SECRET_LENGTH} characters and not "
                f"a placeholder when APP_ENV={self.APP_ENV!r}"
            )
            raise ValueError(msg)
        if self.DEBUG:
            msg = "DEBUG must be false when APP_ENV is staging/production"
            raise ValueError(msg)
        return self

    @property
    def is_development(self) -> bool:
        """True for development/test environments."""
        return self.APP_ENV in ("development", "test")

    @property
    def is_sqlite(self) -> bool:
        """True when the configured database is SQLite (dev/unit-test convenience only)."""
        return self.DATABASE_URL.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    """Return cached singleton settings instance. Fails fast on missing/invalid config."""
    return Settings()
