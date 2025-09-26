"""Add model usage table

Revision ID: 863c43b0ddd3
Revises: e4255c1640a7
Create Date: 2025-09-23 14:01:21.474131

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "863c43b0ddd3"
down_revision: Union[str, Sequence[str], None] = "f20f579831f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "model_usage",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("api_key_id", sa.String(length=36), nullable=True),
        sa.Column("model", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("bucket_start", sa.DateTime(), nullable=False),
        sa.Column("metric_name", sa.Text(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["api_key_id"],
            ["model_api_keys.id"],
            name=op.f("fk_model_usage__api_key_id__model_api_keys"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_model_usage__user_id__users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_usage")),
    )
    # Partial unique indexes to enforce uniqueness for NULL and non-NULL api_key_id separately
    op.create_index(
        "uq_model_usage_bucket_free",
        "model_usage",
        ["user_id", "bucket_start", "metric_name", "model"],
        unique=True,
        postgresql_where=sa.text("api_key_id IS NULL"),
    )
    op.create_index(
        "uq_model_usage_bucket_byok",
        "model_usage",
        ["user_id", "api_key_id", "bucket_start", "metric_name", "model"],
        unique=True,
        postgresql_where=sa.text("api_key_id IS NOT NULL"),
    )
    op.create_index(
        "idx_model_usage_byok_window",
        "model_usage",
        ["user_id", "api_key_id", "bucket_start"],
        unique=False,
    )
    op.create_index(
        "idx_model_usage_free_window",
        "model_usage",
        ["user_id", "bucket_start"],
        unique=False,
        postgresql_where=sa.text("api_key_id IS NULL"),
    )
    op.create_index(op.f("ix_model_usage__api_key_id"), "model_usage", ["api_key_id"], unique=False)
    op.create_index(
        op.f("ix_model_usage__bucket_start"), "model_usage", ["bucket_start"], unique=False
    )
    op.create_index(op.f("ix_model_usage__user_id"), "model_usage", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_model_usage_bucket_byok",
        table_name="model_usage",
        postgresql_where=sa.text("api_key_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_model_usage_bucket_free",
        table_name="model_usage",
        postgresql_where=sa.text("api_key_id IS NULL"),
    )
    op.drop_index(op.f("ix_model_usage__user_id"), table_name="model_usage")
    op.drop_index(op.f("ix_model_usage__bucket_start"), table_name="model_usage")
    op.drop_index(op.f("ix_model_usage__api_key_id"), table_name="model_usage")
    op.drop_index(
        "idx_model_usage_free_window",
        table_name="model_usage",
        postgresql_where=sa.text("api_key_id IS NULL"),
    )
    op.drop_index("idx_model_usage_byok_window", table_name="model_usage")
    op.drop_table("model_usage")
