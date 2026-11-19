"""
ServerGen AI — Database Seed Script.

Creates tables and seeds initial data:
- All system roles
- All permissions
- Role → permission mappings
- Initial admin user

Usage:
    python -m scripts.seed_db
"""

from __future__ import annotations

import asyncio
import sys
import uuid

# Ensure src is importable
sys.path.insert(0, ".")

# Import async session maker
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from src.auth.permissions import (
    DEFAULT_ROLE_PERMISSIONS,
    SystemRole,
    get_permission_resource_action,
)
from src.core.config import get_settings
from src.core.database import get_engine
from src.core.security import hash_password
from src.models import Base
from src.models.role import Permission, Role, RolePermission
from src.models.user import User


async def seed() -> None:
    """Create tables and seed initial data."""
    settings = get_settings()
    engine = get_engine()

    print("=" * 60)
    print("ServerGen AI — Database Seed")
    print("=" * 60)
    print(f"  Database: {settings.DATABASE_URL[:50]}...")
    print(f"  Environment: {settings.APP_ENV}")
    print()

    # ── 1. Create all tables ────────────────────────────────────────
    print("[1/5] Creating tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("  [OK] Tables created")

    # ── 2. Create session ───────────────────────────────────────────
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as db:
        try:
            # ── 3. Seed permissions ─────────────────────────────────
            print("[2/5] Seeding permissions...")
            all_permission_codenames: set[str] = set()
            for perms in DEFAULT_ROLE_PERMISSIONS.values():
                for p in perms:
                    all_permission_codenames.add(str(p))

            permissions_map: dict[str, Permission] = {}
            from sqlalchemy import select

            for codename in sorted(all_permission_codenames):
                # Check if already exists
                result = await db.execute(
                    select(Permission).where(Permission.codename == codename)
                )
                perm = result.scalar_one_or_none()
                if perm is None:
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
            print(f"  [OK] {len(permissions_map)} permissions seeded")

            # ── 4. Seed roles + role-permission mappings ────────────
            print("[3/5] Seeding roles...")
            roles_map: dict[str, Role] = {}
            for system_role in SystemRole:
                result = await db.execute(
                    select(Role).where(Role.name == system_role.value)
                )
                role = result.scalar_one_or_none()
                if role is None:
                    role = Role(
                        id=uuid.uuid4(),
                        name=system_role.value,
                        description=f"System role: {system_role.value}",
                        is_system=True,
                    )
                    db.add(role)
                    await db.flush()
                roles_map[system_role.value] = role
            print(f"  [OK] {len(roles_map)} roles seeded")

            # ── 5. Seed role-permission assignments ─────────────────
            print("[4/5] Assigning permissions to roles...")
            assignment_count = 0
            for system_role, perm_codes in DEFAULT_ROLE_PERMISSIONS.items():
                role = roles_map[system_role.value]
                for perm_code in perm_codes:
                    perm = permissions_map[str(perm_code)]
                    # Check if assignment exists
                    result = await db.execute(
                        select(RolePermission).where(
                            RolePermission.role_id == role.id,
                            RolePermission.permission_id == perm.id,
                        )
                    )
                    if result.scalar_one_or_none() is None:
                        db.add(
                            RolePermission(
                                role_id=role.id, permission_id=perm.id
                            )
                        )
                        assignment_count += 1
            await db.flush()
            print(f"  [OK] {assignment_count} role-permission assignments")

            # ── 6. Seed test users (one per role) ──────────────────
            print("[5/5] Seeding test users (all roles)...")
            test_users = [
                ("admin", "admin@servergen.local", "System Administrator",
                 SystemRole.ADMIN, settings.ADMIN_PASSWORD.get_secret_value()),
                ("operator", "operator@servergen.local", "IT Operator",
                 SystemRole.IT_OPERATOR, "Operator1!"),
                ("analyst", "analyst@servergen.local", "Security Analyst",
                 SystemRole.SECURITY_ANALYST, "Analyst1!"),
                ("manager", "manager@servergen.local", "Department Manager",
                 SystemRole.MANAGER, "Manager1!"),
                ("employee", "employee@servergen.local", "General Employee",
                 SystemRole.GENERAL_EMPLOYEE, "Employee1!"),
            ]

            created = 0
            for uname, email, fullname, sys_role, pwd in test_users:
                result = await db.execute(
                    select(User).where(User.username == uname)
                )
                if result.scalar_one_or_none() is None:
                    role = roles_map[sys_role.value]
                    db.add(User(
                        id=uuid.uuid4(),
                        username=uname,
                        email=email,
                        hashed_password=hash_password(pwd),
                        full_name=fullname,
                        role_id=role.id,
                        is_active=True,
                    ))
                    created += 1
            await db.flush()
            print(f"  [OK] {created} users created")

            await db.commit()

        except Exception:
            await db.rollback()
            raise

    await engine.dispose()

    print()
    print("=" * 60)
    print("  Seed complete!")
    print()
    print("  Start server: python -m uvicorn src.app:app --reload")
    print("  Dashboard:    http://localhost:8000/test")
    print("  API docs:     http://localhost:8000/docs")
    print()
    print("  Test accounts:")
    print("  +----------+--------------------+------------+")
    print("  | Username | Role               | Password   |")
    print("  +----------+--------------------+------------+")
    print("  | admin    | administrator      | admin      |")
    print("  | operator | it_operator        | Operator1! |")
    print("  | analyst  | security_analyst   | Analyst1!  |")
    print("  | manager  | manager            | Manager1!  |")
    print("  | employee | general_employee   | Employee1! |")
    print("  +----------+--------------------+------------+")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(seed())
