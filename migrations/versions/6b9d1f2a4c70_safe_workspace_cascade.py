"""make workspace/account deletion safe on PostgreSQL

Revision ID: 6b9d1f2a4c70
Revises: 95f38ac71e02
"""
from typing import Sequence, Union

from alembic import op


revision: str = "6b9d1f2a4c70"
down_revision: Union[str, Sequence[str], None] = "95f38ac71e02"
branch_labels = None
depends_on = None


CONSTRAINTS = (
    ("runs", "runs_team_id_fkey", "teams", ["team_id"], ["id"], "CASCADE"),
    ("runs", "fk_runs_workflow_id_workflows", "workflows", ["workflow_id"], ["id"], "SET NULL"),
    ("tasks", "tasks_assigned_agent_id_fkey", "agents", ["assigned_agent_id"], ["id"], "SET NULL"),
    ("tasks", "tasks_parent_task_id_fkey", "tasks", ["parent_task_id"], ["id"], "SET NULL"),
    ("run_events", "run_events_task_id_fkey", "tasks", ["task_id"], ["id"], "SET NULL"),
    ("run_events", "run_events_parent_event_id_fkey", "run_events", ["parent_event_id"], ["id"], "SET NULL"),
    ("artifacts", "artifacts_task_id_fkey", "tasks", ["task_id"], ["id"], "SET NULL"),
    ("artifacts", "artifacts_created_by_agent_id_fkey", "agents", ["created_by_agent_id"], ["id"], "SET NULL"),
    ("approvals", "approvals_task_id_fkey", "tasks", ["task_id"], ["id"], "SET NULL"),
    ("approvals", "approvals_requested_by_agent_id_fkey", "agents", ["requested_by_agent_id"], ["id"], "SET NULL"),
)


def _replace_foreign_keys(*, use_delete_actions: bool) -> None:
    """Apply FK changes with a table rebuild when the database is SQLite."""
    if op.get_bind().dialect.name == "sqlite":
        by_table: dict[str, list[tuple[str, str, list[str], list[str], str]]] = {}
        for table, name, target, local, remote, action in CONSTRAINTS:
            by_table.setdefault(table, []).append((name, target, local, remote, action))

        for table, constraints in by_table.items():
            # Historical SQLite tables have unnamed constraints.  Apply the
            # conventional PostgreSQL-style names while reflecting them, then
            # rebuild each affected table once with its replacement FKs.
            with op.batch_alter_table(
                table,
                recreate="always",
                naming_convention={"fk": "%(table_name)s_%(column_0_name)s_fkey"},
            ) as batch_op:
                for name, target, local, remote, action in constraints:
                    batch_op.drop_constraint(name, type_="foreignkey")
                    batch_op.create_foreign_key(
                        name,
                        target,
                        local,
                        remote,
                        ondelete=action if use_delete_actions else None,
                    )
        return

    for table, name, target, local, remote, action in CONSTRAINTS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name,
            table,
            target,
            local,
            remote,
            ondelete=action if use_delete_actions else None,
        )


def upgrade() -> None:
    _replace_foreign_keys(use_delete_actions=True)


def downgrade() -> None:
    _replace_foreign_keys(use_delete_actions=False)
