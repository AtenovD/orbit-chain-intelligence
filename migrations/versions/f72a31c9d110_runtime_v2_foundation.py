"""runtime v2 durable foundation

Revision ID: f72a31c9d110
Revises: 12e66b7a33f1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f72a31c9d110"
down_revision: Union[str, Sequence[str], None] = "12e66b7a33f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("runtime_version", sa.String(length=20), nullable=False, server_default="v2"))
        batch.add_column(sa.Column("plan_revision", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("current_stage", sa.String(length=80), nullable=False, server_default="created"))
        batch.add_column(sa.Column("last_checkpoint_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_runs_runtime_version", ["runtime_version"])

    op.create_table(
        "run_checkpoints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=80), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_run_checkpoint_sequence"),
    )
    op.create_index("ix_run_checkpoints_run_id", "run_checkpoints", ["run_id"])

    op.create_table(
        "run_commands",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("command", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("recipients", sa.JSON(), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_run_commands_run_id", "run_commands", ["run_id"])
    op.create_index("ix_run_commands_status", "run_commands", ["status"])

    op.create_table(
        "task_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "attempt", name="uq_task_attempt"),
    )
    op.create_index("ix_task_attempts_task_id", "task_attempts", ["task_id"])

    op.create_table(
        "tool_calls",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("connection_id", sa.String(length=36), nullable=True),
        sa.Column("tool_name", sa.String(length=180), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("risk", sa.String(length=30), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["connection_id"], ["provider_connections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_calls_run_id", "tool_calls", ["run_id"])
    op.create_index("ix_tool_calls_status", "tool_calls", ["status"])

    op.create_table(
        "memory_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("memory_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("source", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["memory_id"], ["memory_notes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_chunks_memory_id", "memory_chunks", ["memory_id"])

    op.create_table(
        "agent_lessons",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("lesson", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_lessons_agent_id", "agent_lessons", ["agent_id"])
    op.create_index("ix_agent_lessons_status", "agent_lessons", ["status"])


def downgrade() -> None:
    op.drop_table("agent_lessons")
    op.drop_table("memory_chunks")
    op.drop_table("tool_calls")
    op.drop_table("task_attempts")
    op.drop_table("run_commands")
    op.drop_table("run_checkpoints")
    with op.batch_alter_table("runs") as batch:
        batch.drop_index("ix_runs_runtime_version")
        batch.drop_column("last_checkpoint_at")
        batch.drop_column("current_stage")
        batch.drop_column("plan_revision")
        batch.drop_column("runtime_version")
