"""workspace token registry and verdict history

Revision ID: 4f8c2a1d7b90
Revises: 3e2a9f1c7b44
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4f8c2a1d7b90"
down_revision: Union[str, Sequence[str], None] = "3e2a9f1c7b44"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("address", sa.String(length=256), nullable=False),
        sa.Column("chain_id", sa.Integer(), nullable=False, server_default="4663"),
        sa.Column("label", sa.String(length=160), nullable=True),
        sa.Column("symbol", sa.String(length=80), nullable=True),
        sa.Column("name", sa.String(length=300), nullable=True),
        sa.Column("watchlist", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "chain_id", "address", name="uq_token_workspace_chain_address"),
    )
    op.create_index("ix_tokens_workspace_id", "tokens", ["workspace_id"])
    op.create_index("ix_tokens_watchlist", "tokens", ["watchlist"])

    op.create_table(
        "token_verdicts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("artifact_id", sa.String(length=36), nullable=True),
        sa.Column("verdict", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["token_id"], ["tokens.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_token_verdicts_token_id", "token_verdicts", ["token_id"])
    op.create_index("ix_token_verdicts_run_id", "token_verdicts", ["run_id"])
    op.create_index("ix_token_verdicts_artifact_id", "token_verdicts", ["artifact_id"])


def downgrade() -> None:
    op.drop_index("ix_token_verdicts_artifact_id", table_name="token_verdicts")
    op.drop_index("ix_token_verdicts_run_id", table_name="token_verdicts")
    op.drop_index("ix_token_verdicts_token_id", table_name="token_verdicts")
    op.drop_table("token_verdicts")
    op.drop_index("ix_tokens_watchlist", table_name="tokens")
    op.drop_index("ix_tokens_workspace_id", table_name="tokens")
    op.drop_table("tokens")
