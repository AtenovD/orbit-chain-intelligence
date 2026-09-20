"""memory hybrid vectors

Revision ID: f19d7c184b30
Revises: e81a42cd503f
"""
from alembic import op
import sqlalchemy as sa

revision = "f19d7c184b30"
down_revision = "e81a42cd503f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("memory_chunks") as batch:
        batch.add_column(sa.Column("embedding", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("memory_chunks") as batch:
        batch.drop_column("embedding")
