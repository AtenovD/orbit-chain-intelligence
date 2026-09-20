"""paper trading ledger and decision evaluations

Revision ID: d4e8a21f6c90
Revises: c2f4a9d8e1b0
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e8a21f6c90"
down_revision: Union[str, Sequence[str], None] = "c2f4a9d8e1b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_observations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_id", sa.String(length=36), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("quote_symbol", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=160), nullable=False),
        sa.Column("source_ref", sa.String(length=500), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["token_id"], ["tokens.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_id", "source", "source_ref", name="uq_market_observation_source_ref"),
    )
    op.create_index("ix_market_observations_token_id", "market_observations", ["token_id"])
    op.create_index("ix_market_observations_kind", "market_observations", ["kind"])
    op.create_index("ix_market_observations_observed_at", "market_observations", ["observed_at"])

    op.create_table(
        "paper_trades",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_id", sa.String(length=36), nullable=False),
        sa.Column("verdict_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("quote_symbol", sa.String(length=40), nullable=False),
        sa.Column("notional", sa.Float(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("entry_observation_id", sa.String(length=36), nullable=True),
        sa.Column("exit_observation_id", sa.String(length=36), nullable=True),
        sa.Column("fee_bps", sa.Float(), nullable=False),
        sa.Column("slippage_bps", sa.Float(), nullable=False),
        sa.Column("fees_paid", sa.Float(), nullable=False),
        sa.Column("realized_pnl", sa.Float(), nullable=True),
        sa.Column("return_pct", sa.Float(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_reason", sa.String(length=300), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["token_id"], ["tokens.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["verdict_id"], ["token_verdicts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["entry_observation_id"], ["market_observations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["exit_observation_id"], ["market_observations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_paper_trades_token_id", "paper_trades", ["token_id"])
    op.create_index("ix_paper_trades_verdict_id", "paper_trades", ["verdict_id"])
    op.create_index("ix_paper_trades_run_id", "paper_trades", ["run_id"])
    op.create_index("ix_paper_trades_status", "paper_trades", ["status"])

    op.create_table(
        "decision_evaluations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_id", sa.String(length=36), nullable=False),
        sa.Column("verdict_id", sa.String(length=36), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("outcome", sa.String(length=30), nullable=False),
        sa.Column("horizon_seconds", sa.Integer(), nullable=False),
        sa.Column("entry_observation_id", sa.String(length=36), nullable=True),
        sa.Column("exit_observation_id", sa.String(length=36), nullable=True),
        sa.Column("benchmark_return_pct", sa.Float(), nullable=True),
        sa.Column("strategy_return_pct", sa.Float(), nullable=True),
        sa.Column("max_favorable_excursion_pct", sa.Float(), nullable=True),
        sa.Column("max_adverse_excursion_pct", sa.Float(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["token_id"], ["tokens.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["verdict_id"], ["token_verdicts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entry_observation_id"], ["market_observations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["exit_observation_id"], ["market_observations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decision_evaluations_token_id", "decision_evaluations", ["token_id"])
    op.create_index("ix_decision_evaluations_verdict_id", "decision_evaluations", ["verdict_id"])
    op.create_index("ix_decision_evaluations_status", "decision_evaluations", ["status"])


def downgrade() -> None:
    op.drop_index("ix_decision_evaluations_status", table_name="decision_evaluations")
    op.drop_index("ix_decision_evaluations_verdict_id", table_name="decision_evaluations")
    op.drop_index("ix_decision_evaluations_token_id", table_name="decision_evaluations")
    op.drop_table("decision_evaluations")
    op.drop_index("ix_paper_trades_status", table_name="paper_trades")
    op.drop_index("ix_paper_trades_run_id", table_name="paper_trades")
    op.drop_index("ix_paper_trades_verdict_id", table_name="paper_trades")
    op.drop_index("ix_paper_trades_token_id", table_name="paper_trades")
    op.drop_table("paper_trades")
    op.drop_index("ix_market_observations_observed_at", table_name="market_observations")
    op.drop_index("ix_market_observations_kind", table_name="market_observations")
    op.drop_index("ix_market_observations_token_id", table_name="market_observations")
    op.drop_table("market_observations")
