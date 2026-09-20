"""enable the built-in ADHD-friendly output skill for every agent

Revision ID: c2f4a9d8e1b0
Revises: b7d31f60c8a4
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2f4a9d8e1b0"
down_revision: Union[str, Sequence[str], None] = "b7d31f60c8a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("adhd_skill_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("agents", "adhd_skill_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("agents", "adhd_skill_enabled")
