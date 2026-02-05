"""merge heads

Revision ID: 74aec36e7f83
Revises: 272b2376885b, bc66a0277bcd
Create Date: 2026-02-05 11:30:24.562978

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "74aec36e7f83"
down_revision: Union[str, Sequence[str], None] = ("272b2376885b", "bc66a0277bcd")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
