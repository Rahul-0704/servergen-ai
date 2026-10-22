"""
ServerGen AI — Async Database Connection Layer.

SQLAlchemy 2.x async. PostgreSQL (asyncpg) is the supported target; SQLite is
tolerated only for lightweight local/unit-test use and no application SQL
depends on SQLite behaviour.

Engine and session factory are lazily initialised so configuration is loaded
before any connection is made.

TRANSACTION MODEL
    ``get_db`` commits when the request handler returns normally and rolls back
    when it raises. Code that must persist state *before* raising a domain error
    (e.g. failed-login counters, audit records of a denial) must either return a
    result instead of raising, or call ``await db.commit()`` explicitly first.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create the async database engine (lazy initialisation)."""
    global _engine
    if _engine is None:
        from src.core.config import get_settings

        settings = get_settings()
        if settings.is_sqlite:
            _engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)
        else:
            _engine = create_async_engine(
                settings.DATABASE_URL,
                echo=settings.DEBUG,
                pool_size=settings.DB_POOL_SIZE,
                max_overflow=settings.DB_MAX_OVERFLOW,
                pool_pre_ping=True,
                pool_recycle=3600,
            )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory (lazy initialisation)."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,  # required for async — prevents MissingGreenlet
            autoflush=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: one session per request. Commit on success, rollback on error."""
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_database() -> bool:
    """Return True if a trivial query succeeds (used by the readiness probe)."""
    try:
        async with get_session_factory()() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def dispose_engine() -> None:
    """Dispose the engine (application shutdown)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def reset_engine() -> None:
    """Forget the engine and session factory (tests)."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None
