"""Initial schema — Users, Roles, Permissions, RefreshSessions, AuditEvents, ApprovalRequests.

Revision ID: 001
Revises: None
Create Date: 2026-09-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Roles ────────────────────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── Permissions ──────────────────────────────────────────────────────
    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("codename", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("resource", sa.String(50), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
    )

    # ── Role-Permission mapping ──────────────────────────────────────────
    op.create_table(
        "role_permissions",
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "permission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("permissions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )

    # ── Users ────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("hashed_password", sa.Text, nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False, server_default=""),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "failed_login_attempts", sa.Integer, nullable=False, server_default=sa.text("0")
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("failed_login_attempts >= 0", name="ck_users_failed_attempts_nonneg"),
    )

    # ── Refresh Sessions ─────────────────────────────────────────────────
    op.create_table(
        "refresh_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("refresh_token_hash", sa.String(128), nullable=False, index=True),
        sa.Column("family_id", sa.String(36), nullable=False, index=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
    )

    # ── Audit Events ─────────────────────────────────────────────────────
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sequence_number", sa.Integer, unique=True, nullable=False, index=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            index=True,
        ),
        sa.Column("user_id", sa.String(36), nullable=True, index=True),
        sa.Column("role", sa.String(50), nullable=True),
        sa.Column("request_id", sa.String(36), nullable=False, index=True),
        sa.Column("event_type", sa.String(50), nullable=False, index=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource", sa.String(255), nullable=True),
        sa.Column("decision", sa.String(20), nullable=False, server_default="allow"),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="low"),
        sa.Column("agent", sa.String(100), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("tool", sa.String(100), nullable=True),
        sa.Column("metadata_json", postgresql.JSON, nullable=True),
        sa.Column("previous_hash", sa.String(64), nullable=True),
        sa.Column("event_hash", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "decision IN ('allow','deny','require_approval','error')",
            name="ck_audit_decision",
        ),
        sa.CheckConstraint(
            "risk_level IN ('low','medium','high','critical')",
            name="ck_audit_risk_level",
        ),
    )
    op.create_index(
        "ix_audit_events_type_timestamp",
        "audit_events",
        ["event_type", "timestamp"],
    )

    # ── Approval Requests ────────────────────────────────────────────────
    op.create_table(
        "approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(36), nullable=False, index=True),
        sa.Column(
            "requester_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("requester_role", sa.String(50), nullable=False),
        sa.Column("operation_summary", sa.Text, nullable=False),
        sa.Column("task_classification_json", postgresql.JSON, nullable=True),
        sa.Column("risk_assessment_json", postgresql.JSON, nullable=True),
        sa.Column("operation_payload", postgresql.JSON, nullable=True),
        sa.Column("operation_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending", index=True),
        sa.Column(
            "reviewer_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("reviewer_notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            index=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','expired','cancelled')",
            name="ck_approval_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("approval_requests")
    op.drop_index("ix_audit_events_type_timestamp", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("refresh_sessions")
    op.drop_table("users")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
