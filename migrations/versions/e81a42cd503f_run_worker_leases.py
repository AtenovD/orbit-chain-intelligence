"""run worker leases

Revision ID: e81a42cd503f
Revises: db73e15a902c
"""
from alembic import op
import sqlalchemy as sa

revision = "e81a42cd503f"
down_revision = "db73e15a902c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("worker_id", sa.String(length=180), nullable=True))
        batch.add_column(sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_runs_worker_id", ["worker_id"])
        batch.create_index("ix_runs_lease_until", ["lease_until"])


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.drop_index("ix_runs_lease_until")
        batch.drop_index("ix_runs_worker_id")
        batch.drop_column("lease_until")
        batch.drop_column("worker_id")
