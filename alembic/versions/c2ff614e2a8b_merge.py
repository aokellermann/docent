"""merge

Revision ID: c2ff614e2a8b
Revises: 2b81ccac9ef7, 3769d80f60b2
Create Date: 2025-11-29 16:42:17.090158

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "c2ff614e2a8b"
down_revision: Union[str, Sequence[str], None] = ("2b81ccac9ef7", "3769d80f60b2")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
