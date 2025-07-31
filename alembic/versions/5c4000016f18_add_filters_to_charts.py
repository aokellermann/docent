"""Add filters to charts

Revision ID: 5c4000016f18
Revises: e68cf49cd5a2
Create Date: 2025-07-30 11:16:50.129988

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5c4000016f18"
down_revision: Union[str, Sequence[str], None] = "e68cf49cd5a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Step 1: Add collection_id as nullable first
    op.add_column("charts", sa.Column("collection_id", sa.String(length=36), nullable=True))

    # Step 2: Populate collection_id from the view's collection_id
    op.execute(
        """
        UPDATE charts
        SET collection_id = views.collection_id
        FROM views
        WHERE charts.view_id = views.id
    """
    )

    # Step 3: Make collection_id non-nullable now that it's populated
    op.alter_column("charts", "collection_id", nullable=False)

    # Step 4: Add other columns and continue with the migration
    op.add_column(
        "charts",
        sa.Column("runs_filter_dict", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.drop_index(op.f("ix_charts__view_id"), table_name="charts")
    op.create_index(op.f("ix_charts__collection_id"), "charts", ["collection_id"], unique=False)
    op.drop_constraint(op.f("fk_charts__view_id__views"), "charts", type_="foreignkey")
    op.create_foreign_key(
        op.f("fk_charts__collection_id__collections"),
        "charts",
        "collections",
        ["collection_id"],
        ["id"],
    )
    op.drop_column("charts", "view_id")
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # Note: This downgrade cannot perfectly restore view_id relationships
    # since we're losing the specific view association. This adds view_id
    # but cannot populate it with the original view data.
    op.add_column(
        "charts", sa.Column("view_id", sa.VARCHAR(length=36), autoincrement=False, nullable=True)
    )

    # Create a default view for each collection if needed for downgrade
    # This is a best-effort approach since we lose the original view association
    op.execute(
        """
        UPDATE charts
        SET view_id = (
            SELECT v.id
            FROM views v
            WHERE v.collection_id = charts.collection_id
            LIMIT 1
        )
        WHERE view_id IS NULL
    """
    )

    op.alter_column("charts", "view_id", nullable=False)
    op.drop_constraint(op.f("fk_charts__collection_id__collections"), "charts", type_="foreignkey")
    op.create_foreign_key(op.f("fk_charts__view_id__views"), "charts", "views", ["view_id"], ["id"])
    op.drop_index(op.f("ix_charts__collection_id"), table_name="charts")
    op.create_index(op.f("ix_charts__view_id"), "charts", ["view_id"], unique=False)
    op.drop_column("charts", "runs_filter_dict")
    op.drop_column("charts", "collection_id")
    # ### end Alembic commands ###
