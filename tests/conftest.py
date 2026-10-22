"""
ServerGen AI — Test Configuration and Fixtures.

Environment variables are set BEFORE any application imports.
Unit tests use in-memory SQLite for speed and isolation.
Integration tests should use PostgreSQL (see tests/integration/conftest.py).
"""

from __future__ import annotations

import os

# ── Set test environment BEFORE any application imports ──────────────────
os.environ["APP_ENV"] = "test"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-not-for-production-use-only-testing-1234567890"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://servergen:changeme@localhost:5432/servergen_test"
os.environ["ADMIN_PASSWORD"] = "test-admin-password-not-real"

from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.core.config import get_settings
from src.core.database import get_db
from src.models import Base

# Clear cached settings so test env vars take effect
get_settings.cache_clear()

# SQLite for unit tests (fast, isolated, no external dependencies)
SQLITE_TEST_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(SQLITE_TEST_URL, echo=False)
TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(loop_scope="session", scope="session", autouse=True)
async def setup_test_database() -> AsyncGenerator[None, None]:
    """Create all tables in the in-memory SQLite database for the test session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture()
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated database session for each test."""
    async with TestingSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture()
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP test client with overridden database dependency."""
    from src.app import create_app

    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.clear()
