"""drop metadata registry

Revision ID: d7e9f1a2b3c4
Revises: ba664d6bf692
Create Date: 2026-02-12 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7e9f1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "d3a1f7c84e92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop metadata_value_stats materialized view and metadata_observations table."""
    op.execute("DROP MATERIALIZED VIEW IF EXISTS metadata_value_stats")
    op.drop_table("metadata_observations")


def downgrade() -> None:
    """Re-creation not supported — metadata registry has been removed."""
    raise NotImplementedError("Cannot restore dropped metadata registry")
