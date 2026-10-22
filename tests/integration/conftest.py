"""
ServerGen AI — PostgreSQL Integration Test Fixtures.

Connects to a live PostgreSQL cluster and verifies database operations
against real PostgreSQL tables, advisory locks, UUIDs, and JSON types.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from src.core.database import get_db
from src.models import Base

# Target local PostgreSQL test database
POSTGRES_TEST_URL = os.environ.get(
    "POSTGRES_TEST_URL",
    "postgresql+asyncpg://servergen@127.0.0.1:5432/servergen_test",
)

pg_test_engine = create_async_engine(
    POSTGRES_TEST_URL,
    echo=False,
    poolclass=NullPool,
)
PgTestingSessionLocal = async_sessionmaker(
    bind=pg_test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(loop_scope="session", scope="session", autouse=True)
async def setup_postgres_database() -> AsyncGenerator[None, None]:
    """Verify PostgreSQL connectivity and create all tables in servergen_test."""
    try:
        async with pg_test_engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(
            f"PostgreSQL integration tests skipped (cannot connect to {POSTGRES_TEST_URL}): {exc}"
        )

    # Create tables
    async with pg_test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    # Teardown
    await pg_test_engine.dispose()


@pytest_asyncio.fixture()
async def pg_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated database session for PostgreSQL integration tests."""
    async with PgTestingSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture()
async def pg_client(pg_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP test client backed by live PostgreSQL."""
    from src.app import create_app

    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield pg_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
