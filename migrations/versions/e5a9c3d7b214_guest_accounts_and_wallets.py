"""guest accounts and wallet sign-in

Revision ID: e5a9c3d7b214
Revises: d4e8a21f6c90
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5a9c3d7b214"
down_revision: Union[str, Sequence[str], None] = "d4e8a21f6c90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_guest", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("wallet_address", sa.String(length=42), nullable=True))
    op.create_index("ix_users_is_guest", "users", ["is_guest"])
    op.create_index("ix_users_wallet_address", "users", ["wallet_address"], unique=True)
    op.create_table(
        "wallet_nonces",
        sa.Column("nonce", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("nonce"),
    )
    op.create_index("ix_wallet_nonces_created_at", "wallet_nonces", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_wallet_nonces_created_at", table_name="wallet_nonces")
    op.drop_table("wallet_nonces")
    op.drop_index("ix_users_wallet_address", table_name="users")
    op.drop_index("ix_users_is_guest", table_name="users")
    op.drop_column("users", "wallet_address")
    op.drop_column("users", "is_guest")
