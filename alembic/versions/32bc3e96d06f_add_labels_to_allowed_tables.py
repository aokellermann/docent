"""add labels to allowed tables

Revision ID: 32bc3e96d06f
Revises: 1c3e7b686e91
Create Date: 2025-11-12 16:06:18.964476

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "32bc3e96d06f"
down_revision: Union[str, Sequence[str], None] = "1c3e7b686e91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DQL_ROLE = "docent_dql_reader"


def upgrade() -> None:
    """Allow the DQL role to read the labels table."""
    op.execute(f"GRANT SELECT ON labels TO {_DQL_ROLE};")


def downgrade() -> None:
    """Revoke the DQL role's ability to read the labels table."""
    op.execute(f"REVOKE SELECT ON labels FROM {_DQL_ROLE};")
