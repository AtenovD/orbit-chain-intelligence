"""public launch security, verification and admin analytics

Revision ID: 9a71c66d4e21
Revises: 1d85c7f4a2b9
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9a71c66d4e21"
down_revision: Union[str, Sequence[str], None] = "1d85c7f4a2b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing accounts predate confirmation: preserve access, while all new
    # registrations receive the ORM default of False after this migration.
    op.add_column("users", sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("users", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_is_superuser", "users", ["is_superuser"])
    op.create_index("ix_users_email_verified", "users", ["email_verified"])
    op.create_index("ix_users_last_seen_at", "users", ["last_seen_at"])
    # SQLite cannot drop a server default without rebuilding the table. ORM
    # inserts always send the False default for new registrations, so keeping
    # the migration-time default there is harmless for local development.
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("users", "email_verified", server_default=None)
    op.add_column("auth_sessions", sa.Column("ip_address", sa.String(length=64), nullable=True))
    op.add_column("auth_sessions", sa.Column("user_agent", sa.String(length=500), nullable=True))
    op.add_column("auth_sessions", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_email_verification_tokens_user_id", "email_verification_tokens", ["user_id"])
    op.create_index("ix_email_verification_tokens_token_hash", "email_verification_tokens", ["token_hash"], unique=True)
    op.create_table(
        "daily_visits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("day", sa.DateTime(timezone=True), nullable=False),
        sa.Column("visitor_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("day", "visitor_hash", name="uq_daily_visit"),
    )
    op.create_index("ix_daily_visits_day", "daily_visits", ["day"])
    op.create_index("ix_daily_visits_visitor_hash", "daily_visits", ["visitor_hash"])
    op.create_index("ix_daily_visits_user_id", "daily_visits", ["user_id"])
    op.create_table(
        "api_rate_limits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=100), nullable=False),
        sa.Column("subject_hash", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "subject_hash", "window_started_at", name="uq_rate_limit_window"),
    )
    op.create_index("ix_api_rate_limits_scope", "api_rate_limits", ["scope"])
    op.create_index("ix_api_rate_limits_subject_hash", "api_rate_limits", ["subject_hash"])
    op.create_index("ix_api_rate_limits_window_started_at", "api_rate_limits", ["window_started_at"])


def downgrade() -> None:
    op.drop_table("api_rate_limits")
    op.drop_table("daily_visits")
    op.drop_table("email_verification_tokens")
    op.drop_column("auth_sessions", "last_seen_at")
    op.drop_column("auth_sessions", "user_agent")
    op.drop_column("auth_sessions", "ip_address")
    op.drop_column("users", "last_seen_at")
    op.drop_column("users", "email_verified")
    op.drop_column("users", "is_superuser")
