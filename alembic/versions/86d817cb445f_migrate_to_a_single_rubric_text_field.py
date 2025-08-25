"""migrate to a single rubric_text field

Revision ID: 86d817cb445f
Revises: 975db2dd2fb3
Create Date: 2025-08-25 11:54:08.679277

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "86d817cb445f"
down_revision: Union[str, Sequence[str], None] = "975db2dd2fb3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _combine_rubric_text(
    high_level_description: str | None,
    inclusion_rules: list[str] | None,
    exclusion_rules: list[str] | None,
) -> str:
    """Create a single rubric_text string from legacy columns.

    The format groups the sections with headers and bullet points for rules.
    """
    hld = (high_level_description or "").strip()
    inc = [r for r in (inclusion_rules or []) if (r or "").strip()]
    exc = [r for r in (exclusion_rules or []) if (r or "").strip()]

    parts: list[str] = []
    if hld:
        parts.append(hld)
    if inc:
        bullets = "\n".join(f"- {rule.strip()}" for rule in inc)
        parts.append("Inclusion rules:\n" + bullets)
    if exc:
        bullets = "\n".join(f"- {rule.strip()}" for rule in exc)
        parts.append("Exclusion rules:\n" + bullets)

    combined = "\n\n".join(parts).strip()
    # Ensure we don't return an empty string if all legacy fields were empty
    return combined or hld or ""


def upgrade() -> None:
    """Upgrade schema."""
    # 1) Add the new column as nullable so we can backfill existing rows safely
    op.add_column("rubrics", sa.Column("rubric_text", sa.Text(), nullable=True))

    # 2) Backfill rubric_text using legacy columns
    connection = op.get_bind()
    result = connection.execute(
        sa.text(
            """
            SELECT id, version, high_level_description, inclusion_rules, exclusion_rules
            FROM rubrics
            """
        )
    )

    # Use mappings() to get dict-like rows regardless of driver
    for row in result.mappings():
        combined_text = _combine_rubric_text(
            row.get("high_level_description"),
            row.get("inclusion_rules"),
            row.get("exclusion_rules"),
        )
        connection.execute(
            sa.text(
                """
                UPDATE rubrics
                SET rubric_text = :rubric_text
                WHERE id = :id AND version = :version
                """
            ),
            {
                "rubric_text": combined_text,
                "id": row["id"],
                "version": row["version"],
            },
        )

    # 3) Enforce NOT NULL after backfill
    op.alter_column("rubrics", "rubric_text", nullable=False)

    # Make the old columns nullable
    op.alter_column("rubrics", "high_level_description", existing_type=sa.TEXT(), nullable=True)
    op.alter_column(
        "rubrics",
        "inclusion_rules",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
    )
    op.alter_column(
        "rubrics",
        "exclusion_rules",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
    )


def downgrade() -> None:
    pass
