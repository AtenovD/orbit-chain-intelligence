"""merge token registry and workspace cascade migration heads

Revision ID: 77c19a5e2d4f
Revises: 4f8c2a1d7b90, 6b9d1f2a4c70
"""

from typing import Sequence, Union


revision: str = "77c19a5e2d4f"
down_revision: Union[str, Sequence[str], None] = ("4f8c2a1d7b90", "6b9d1f2a4c70")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Join independent schema branches; each branch applies its own DDL."""


def downgrade() -> None:
    """Restore the two parent revision markers without changing schema."""
