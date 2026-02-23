"""add composite index on agent_runs(collection_id, created_at)

Revision ID: d3a1f7c84e92
Revises: ba664d6bf692
Create Date: 2026-02-21 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3a1f7c84e92"
down_revision: Union[str, Sequence[str], None] = "ba664d6bf692"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use CONCURRENTLY to avoid blocking writes on large tables.
    # This requires running outside a transaction.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "idx_agent_runs_collection_created_at "
            "ON agent_runs (collection_id, created_at)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_agent_runs_collection_created_at")
