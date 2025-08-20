"""fix created_at default for transcripts and groups

Revision ID: 5c5e0f0e7d18
Revises: 0104b68ff3a5
Create Date: 2025-08-19 19:27:37.106072

"""

from typing import Sequence, Union

from sqlalchemy import func

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5c5e0f0e7d18"
down_revision: Union[str, Sequence[str], None] = "0104b68ff3a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Update transcript_groups.created_at to use UTC timezone
    op.alter_column(
        "transcript_groups",
        "created_at",
        server_default=func.timezone("UTC", func.now()),  # type: ignore
    )

    # Update transcripts.created_at to use UTC timezone
    op.alter_column(
        "transcripts",
        "created_at",
        server_default=func.timezone("UTC", func.now()),  # type: ignore
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Revert transcript_groups.created_at to use func.now()
    op.alter_column(
        "transcript_groups",
        "created_at",
        server_default=func.now(),  # type: ignore
    )

    # Revert transcripts.created_at to use func.now()
    op.alter_column(
        "transcripts",
        "created_at",
        server_default=func.now(),  # type: ignore
    )
