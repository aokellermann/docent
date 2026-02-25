"""add collection_counts materialized view

Revision ID: e4b2c8a1f397
Revises: d7e9f1a2b3c4
Create Date: 2026-02-23 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4b2c8a1f397"
down_revision: Union[str, Sequence[str], None] = "d7e9f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create collection_counts materialized view."""
    op.execute("""
        CREATE MATERIALIZED VIEW collection_counts AS
        SELECT
            c.id AS collection_id,
            COALESCE(ar.cnt, 0)::integer AS agent_run_count,
            COALESCE(r.cnt, 0)::integer AS rubric_count,
            COALESCE(ls.cnt, 0)::integer AS label_set_count
        FROM collections c
        LEFT JOIN (
            SELECT collection_id, COUNT(*) AS cnt
            FROM agent_runs
            GROUP BY collection_id
        ) ar ON ar.collection_id = c.id
        LEFT JOIN (
            SELECT collection_id, COUNT(DISTINCT id) AS cnt
            FROM rubrics
            GROUP BY collection_id
        ) r ON r.collection_id = c.id
        LEFT JOIN (
            SELECT collection_id, COUNT(*) AS cnt
            FROM label_sets
            GROUP BY collection_id
        ) ls ON ls.collection_id = c.id
    """)
    # Unique index required for REFRESH MATERIALIZED VIEW CONCURRENTLY
    op.execute("""
        CREATE UNIQUE INDEX ix_collection_counts_id
        ON collection_counts (collection_id)
    """)


def downgrade() -> None:
    """Drop collection_counts materialized view."""
    op.execute("DROP MATERIALIZED VIEW IF EXISTS collection_counts")
