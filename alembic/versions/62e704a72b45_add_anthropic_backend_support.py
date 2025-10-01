"""add_anthropic_backend_support

Revision ID: 62e704a72b45
Revises: 65aa64407982
Create Date: 2025-10-01 14:38:33.967669

Consolidates 4 migrations:
- dd7e9d012bb8: add_anthropic_compatible_backend_table
- 388e3d4f53b5: add_anthropic_backend_support_to_experiments
- 2e4edee860e0: add_backend_type_check_constraint
- f0bd6b2f0d7c: add_thinking_budget_check_constraint

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "62e704a72b45"
down_revision: Union[str, Sequence[str], None] = "65aa64407982"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add Anthropic backend support."""

    # ===================================================================
    # 1. Create anthropic_compatible_backends table
    # ===================================================================
    op.create_table(
        "anthropic_compatible_backends",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=False),
        sa.Column("thinking_type", sa.Text(), nullable=True),
        sa.Column("thinking_budget_tokens", sa.Integer(), nullable=True),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_anthropic_compatible_backends")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["investigator_workspaces.id"],
            name=op.f("fk_anthropic_compatible_backends__workspace_id__investigator_workspaces"),
        ),
    )
    op.create_index(
        op.f("ix_anthropic_compatible_backends_workspace_id"),
        "anthropic_compatible_backends",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_anthropic_compatible_backends_deleted_at"),
        "anthropic_compatible_backends",
        ["deleted_at"],
        unique=False,
    )

    # Add check constraint for thinking budget
    op.create_check_constraint(
        "check_thinking_budget_required",
        "anthropic_compatible_backends",
        "(thinking_type != 'enabled' OR thinking_budget_tokens IS NOT NULL)",
    )

    # ===================================================================
    # 2. Update counterfactual experiments to support both backend types
    # ===================================================================

    # Add backend_type column (default to 'openai_compatible' for existing rows)
    op.add_column(
        "counterfactual_experiment_configs",
        sa.Column(
            "backend_type",
            sa.String(50),
            nullable=False,
            server_default="openai_compatible",
        ),
    )
    # Remove server default after backfill
    op.alter_column(
        "counterfactual_experiment_configs",
        "backend_type",
        server_default=None,
    )

    # Add anthropic_compatible_backend_id column (nullable)
    op.add_column(
        "counterfactual_experiment_configs",
        sa.Column("anthropic_compatible_backend_id", sa.String(36), nullable=True),
    )
    op.create_index(
        op.f("ix_counterfactual_experiment_configs_anthropic_compatible_backend_id"),
        "counterfactual_experiment_configs",
        ["anthropic_compatible_backend_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f(
            "fk_counterfactual_experiment_configs__anthropic_compatible_backend_id__anthropic_compatible_backends"
        ),
        "counterfactual_experiment_configs",
        "anthropic_compatible_backends",
        ["anthropic_compatible_backend_id"],
        ["id"],
    )

    # Make openai_compatible_backend_id nullable
    op.alter_column(
        "counterfactual_experiment_configs",
        "openai_compatible_backend_id",
        existing_type=sa.String(36),
        nullable=True,
    )

    # Add check constraint for backend type consistency
    op.create_check_constraint(
        "check_backend_type_consistency",
        "counterfactual_experiment_configs",
        """
        (backend_type = 'openai_compatible' AND openai_compatible_backend_id IS NOT NULL AND anthropic_compatible_backend_id IS NULL)
        OR
        (backend_type = 'anthropic_compatible' AND anthropic_compatible_backend_id IS NOT NULL AND openai_compatible_backend_id IS NULL)
        """,
    )

    # ===================================================================
    # 3. Add Anthropic backend support to simple rollout experiments
    # ===================================================================

    # Create junction table for Anthropic backends
    op.create_table(
        "simple_rollout_config_anthropic_backends",
        sa.Column("experiment_config_id", sa.String(36), nullable=False),
        sa.Column("backend_id", sa.String(36), nullable=False),
        sa.PrimaryKeyConstraint("experiment_config_id", "backend_id"),
        sa.ForeignKeyConstraint(
            ["experiment_config_id"],
            ["simple_rollout_experiment_configs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["backend_id"],
            ["anthropic_compatible_backends.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        op.f("ix_simple_rollout_config_anthropic_backends_experiment_config_id"),
        "simple_rollout_config_anthropic_backends",
        ["experiment_config_id"],
    )
    op.create_index(
        op.f("ix_simple_rollout_config_anthropic_backends_backend_id"),
        "simple_rollout_config_anthropic_backends",
        ["backend_id"],
    )


def downgrade() -> None:
    """Downgrade schema - remove Anthropic backend support."""

    # Remove Anthropic backend support from simple rollout experiments
    op.drop_index(
        op.f("ix_simple_rollout_config_anthropic_backends_backend_id"),
        table_name="simple_rollout_config_anthropic_backends",
    )
    op.drop_index(
        op.f("ix_simple_rollout_config_anthropic_backends_experiment_config_id"),
        table_name="simple_rollout_config_anthropic_backends",
    )
    op.drop_table("simple_rollout_config_anthropic_backends")

    # Revert counterfactual experiments changes
    op.drop_constraint(
        "check_backend_type_consistency", "counterfactual_experiment_configs", type_="check"
    )

    op.alter_column(
        "counterfactual_experiment_configs",
        "openai_compatible_backend_id",
        existing_type=sa.String(36),
        nullable=False,
    )
    op.drop_constraint(
        op.f(
            "fk_counterfactual_experiment_configs__anthropic_compatible_backend_id__anthropic_compatible_backends"
        ),
        "counterfactual_experiment_configs",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_counterfactual_experiment_configs_anthropic_compatible_backend_id"),
        table_name="counterfactual_experiment_configs",
    )
    op.drop_column("counterfactual_experiment_configs", "anthropic_compatible_backend_id")
    op.drop_column("counterfactual_experiment_configs", "backend_type")

    # Remove anthropic_compatible_backends table
    op.drop_constraint(
        "check_thinking_budget_required", "anthropic_compatible_backends", type_="check"
    )
    op.drop_index(
        op.f("ix_anthropic_compatible_backends_deleted_at"),
        table_name="anthropic_compatible_backends",
    )
    op.drop_index(
        op.f("ix_anthropic_compatible_backends_workspace_id"),
        table_name="anthropic_compatible_backends",
    )
    op.drop_table("anthropic_compatible_backends")
