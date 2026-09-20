"""classify registry records as token or NFT collection

Revision ID: 1d85c7f4a2b9
Revises: 77c19a5e2d4f
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1d85c7f4a2b9"
down_revision: Union[str, Sequence[str], None] = "77c19a5e2d4f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tokens",
        sa.Column("asset_kind", sa.String(length=16), nullable=False, server_default="token"),
    )


def downgrade() -> None:
    op.drop_column("tokens", "asset_kind")
