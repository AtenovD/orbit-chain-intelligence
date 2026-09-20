"""daily usage quota

Revision ID: b7d31f60c8a4
Revises: 4c9e5b7a2d11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7d31f60c8a4"
down_revision: Union[str, Sequence[str], None] = "4c9e5b7a2d11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_usage",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("day", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("research_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("day", "user_id", name="uq_daily_usage"),
    )
    op.create_index("ix_daily_usage_day", "daily_usage", ["day"])
    op.create_index("ix_daily_usage_user_id", "daily_usage", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_daily_usage_user_id", table_name="daily_usage")
    op.drop_index("ix_daily_usage_day", table_name="daily_usage")
    op.drop_table("daily_usage")
