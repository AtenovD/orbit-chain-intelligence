"""agent skill slot

Revision ID: 8a20d1f44c2e
Revises: 568bc446df4d
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "8a20d1f44c2e"
down_revision: Union[str, Sequence[str], None] = "568bc446df4d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("skill_name", sa.String(length=120), nullable=True))
    op.add_column("agents", sa.Column("skill_description", sa.Text(), nullable=True))
    op.add_column("agents", sa.Column("skill_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "skill_prompt")
    op.drop_column("agents", "skill_description")
    op.drop_column("agents", "skill_name")
