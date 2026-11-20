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
            from sqlalchemy import event

            _engine = create_async_engine(
                settings.DATABASE_URL,
                echo=settings.DEBUG,
                connect_args={"timeout": 60.0},
            )

            @event.listens_for(_engine.sync_engine, "connect")
            def _set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=60000")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
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


async def initialize_and_seed_database() -> None:
    """
    Automatic zero-setup startup hook:
    1. Creates all database tables if missing.
    2. Runs schema synchronizations (e.g. SQLite vault_scope columns).
    3. Seeds default permissions, system roles, and test users if empty.
    """
    import logging
    import uuid

    from src.auth.permissions import (
        DEFAULT_ROLE_PERMISSIONS,
        SystemRole,
        get_permission_resource_action,
    )
    from src.core.config import get_settings
    from src.core.security import hash_password
    from src.models import Base
    from src.models.role import Permission, Role, RolePermission
    from src.models.user import User

    log = logging.getLogger("servergen.database")
    engine = get_engine()
    settings = get_settings()

    # 1. Create tables & execute schema synchronizations
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # SQLite schema patches (role vault column propagation)
        if settings.is_sqlite:
            try:
                res = await conn.execute(text("PRAGMA table_info(documents)"))
                doc_cols = [r[1] for r in res.fetchall()]
                if "vault_scope" not in doc_cols:
                    await conn.execute(
                        text(
                            "ALTER TABLE documents ADD COLUMN vault_scope VARCHAR(50) "
                            "NOT NULL DEFAULT 'all'"
                        )
                    )
                    log.info("SQLite patch: Added 'vault_scope' to 'documents'")
            except Exception as e:
                log.debug("SQLite documents patch check skipped: %s", e)

            try:
                res_c = await conn.execute(text("PRAGMA table_info(document_chunks)"))
                chunk_cols = [r[1] for r in res_c.fetchall()]
                if "vault_scope" not in chunk_cols:
                    await conn.execute(
                        text(
                            "ALTER TABLE document_chunks ADD COLUMN vault_scope VARCHAR(50) "
                            "NOT NULL DEFAULT 'all'"
                        )
                    )
                    log.info("SQLite patch: Added 'vault_scope' to 'document_chunks'")
            except Exception as e:
                log.debug("SQLite chunks patch check skipped: %s", e)

    # 2. Seed initial roles & accounts if empty
    factory = get_session_factory()
    async with factory() as db:
        try:
            from sqlalchemy import select

            res_roles = await db.execute(select(Role).limit(1))
            if res_roles.scalar_one_or_none() is None:
                log.info("Database roles table is empty. Executing initial system seed...")

                # Seed permissions
                permissions_map: dict[str, Permission] = {}
                all_perm_codes: set[str] = set()
                for perms in DEFAULT_ROLE_PERMISSIONS.values():
                    for p in perms:
                        all_perm_codes.add(str(p))

                for codename in sorted(all_perm_codes):
                    resource, action = get_permission_resource_action(codename)
                    perm = Permission(
                        id=uuid.uuid4(),
                        codename=codename,
                        description=f"{resource} {action}",
                        resource=resource,
                        action=action,
                    )
                    db.add(perm)
                    permissions_map[codename] = perm
                await db.flush()

                # Seed roles
                roles_map: dict[str, Role] = {}
                for sys_role in SystemRole:
                    role_obj = Role(
                        id=uuid.uuid4(),
                        name=sys_role.value,
                        description=f"System role: {sys_role.value}",
                        is_system=True,
                    )
                    db.add(role_obj)
                    roles_map[sys_role.value] = role_obj
                await db.flush()

                # Seed assignments
                for sys_role, perm_codes in DEFAULT_ROLE_PERMISSIONS.items():
                    role_obj = roles_map[sys_role.value]
                    for perm_code in perm_codes:
                        perm_obj = permissions_map[str(perm_code)]
                        db.add(RolePermission(role_id=role_obj.id, permission_id=perm_obj.id))
                await db.flush()

                # Seed default users
                test_users = [
                    (
                        "admin",
                        "admin@servergen.local",
                        "System Administrator",
                        SystemRole.ADMIN,
                        settings.ADMIN_PASSWORD.get_secret_value(),
                    ),
                    (
                        "manager",
                        "manager@servergen.local",
                        "Department Manager",
                        SystemRole.MANAGER,
                        "Manager1!",
                    ),
                    (
                        "operator",
                        "operator@servergen.local",
                        "IT Operator",
                        SystemRole.IT_OPERATOR,
                        "Operator1!",
                    ),
                    (
                        "analyst",
                        "analyst@servergen.local",
                        "Security Analyst",
                        SystemRole.SECURITY_ANALYST,
                        "Analyst1!",
                    ),
                    (
                        "employee",
                        "employee@servergen.local",
                        "General Employee",
                        SystemRole.GENERAL_EMPLOYEE,
                        "Employee1!",
                    ),
                ]
                for uname, email, fullname, sys_role, pwd in test_users:
                    role_obj = roles_map[sys_role.value]
                    db.add(
                        User(
                            id=uuid.uuid4(),
                            username=uname,
                            email=email,
                            hashed_password=hash_password(pwd),
                            full_name=fullname,
                            role_id=role_obj.id,
                            is_active=True,
                        )
                    )
                await db.commit()
                log.info(
                    "Initial system seed completed: 5 default roles, permissions, "
                    "and test accounts active."
                )
        except Exception as exc:
            await db.rollback()
            log.warning("Database seeding check warning: %s", exc)
