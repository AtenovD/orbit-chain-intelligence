"""set team supervisor reference to null when an agent is removed

Revision ID: 95f38ac71e02
Revises: 3e2a9f1c7b44
"""
from typing import Sequence, Union

from alembic import op


revision: str = "95f38ac71e02"
down_revision: Union[str, Sequence[str], None] = "3e2a9f1c7b44"
branch_labels = None
depends_on = None


def _replace_supervisor_foreign_key(*, ondelete: str | None) -> None:
    """Recreate the supervisor FK on SQLite, which cannot ALTER constraints."""
    options = {
        "recreate": "always",
        # The initial SQLite schema has an unnamed FK.  Give its reflected
        # constraint the same deterministic name used by PostgreSQL so it can
        # be dropped during the batch-table rebuild.
        "naming_convention": {"fk": "%(table_name)s_%(column_0_name)s_fkey"},
    }
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("teams", **options) as batch_op:
            batch_op.drop_constraint("teams_supervisor_agent_id_fkey", type_="foreignkey")
            batch_op.create_foreign_key(
                "teams_supervisor_agent_id_fkey",
                "agents",
                ["supervisor_agent_id"],
                ["id"],
                ondelete=ondelete,
            )
        return

    op.drop_constraint("teams_supervisor_agent_id_fkey", "teams", type_="foreignkey")
    op.create_foreign_key(
        "teams_supervisor_agent_id_fkey",
        "teams",
        "agents",
        ["supervisor_agent_id"],
        ["id"],
        ondelete=ondelete,
    )


def upgrade() -> None:
    _replace_supervisor_foreign_key(ondelete="SET NULL")


def downgrade() -> None:
    _replace_supervisor_foreign_key(ondelete=None)
