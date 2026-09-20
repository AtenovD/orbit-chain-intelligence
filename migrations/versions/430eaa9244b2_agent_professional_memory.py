"""agent professional memory

Revision ID: 430eaa9244b2
Revises: 12e66b7a33f1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "430eaa9244b2"
down_revision: Union[str, Sequence[str], None] = "12e66b7a33f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("professional_memory", sa.Text(), nullable=False, server_default=""))
    op.add_column("agents", sa.Column("lessons_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("agents", sa.Column("experience_level", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("agents", "experience_level")
    op.drop_column("agents", "lessons_count")
    op.drop_column("agents", "professional_memory")
