"""file assets

Revision ID: db73e15a902c
Revises: c84722f901e0
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "db73e15a902c"
down_revision: Union[str, Sequence[str], None] = "c84722f901e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "file_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("uploaded_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("mime_type", sa.String(length=160), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_path", sa.String(length=1000), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_file_assets_workspace_id", "file_assets", ["workspace_id"])
    op.create_index("ix_file_assets_sha256", "file_assets", ["sha256"])
    op.create_index("ix_file_assets_status", "file_assets", ["status"])


def downgrade() -> None:
    op.drop_table("file_assets")
