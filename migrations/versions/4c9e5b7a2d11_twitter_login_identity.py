"""store X identity and encrypted credentials on Orbit users

Revision ID: 4c9e5b7a2d11
Revises: 9a71c66d4e21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4c9e5b7a2d11"
down_revision: Union[str, Sequence[str], None] = "9a71c66d4e21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("twitter_user_id", sa.String(length=80), nullable=True))
    op.add_column("users", sa.Column("twitter_profile", sa.JSON(), nullable=True))
    op.add_column("users", sa.Column("twitter_credentials", sa.Text(), nullable=True))
    op.create_index("ix_users_twitter_user_id", "users", ["twitter_user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_twitter_user_id", table_name="users")
    op.drop_column("users", "twitter_credentials")
    op.drop_column("users", "twitter_profile")
    op.drop_column("users", "twitter_user_id")
