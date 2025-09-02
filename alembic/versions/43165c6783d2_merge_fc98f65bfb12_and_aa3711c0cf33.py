"""merge fc98f65bfb12 and aa3711c0cf33

Revision ID: 43165c6783d2
Revises: fc98f65bfb12, aa3711c0cf33
Create Date: 2025-08-28 19:22:49.446581

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "43165c6783d2"
down_revision: Union[str, Sequence[str], None] = ("fc98f65bfb12", "aa3711c0cf33")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
