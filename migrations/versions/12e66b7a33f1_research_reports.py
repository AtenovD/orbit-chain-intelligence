"""research reports

Revision ID: 12e66b7a33f1
Revises: 8a20d1f44c2e
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "12e66b7a33f1"
down_revision: Union[str, Sequence[str], None] = "8a20d1f44c2e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("depth", sa.String(length=20), nullable=False),
        sa.Column("requested_sources", sa.JSON(), nullable=False),
        sa.Column("source_status", sa.JSON(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("report", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_research_reports_workspace_id"), "research_reports", ["workspace_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_research_reports_workspace_id"), table_name="research_reports")
    op.drop_table("research_reports")
