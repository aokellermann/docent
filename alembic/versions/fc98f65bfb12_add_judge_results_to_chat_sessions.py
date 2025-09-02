"""Add judge results to chat sessions

Revision ID: fc98f65bfb12
Revises: 86d817cb445f
Create Date: 2025-08-27 11:17:46.777609

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fc98f65bfb12"
down_revision: Union[str, Sequence[str], None] = "86d817cb445f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # Make agent_run_ids column nullable
    op.alter_column("chat_sessions", "agent_run_ids", nullable=True)

    # Add agent_run_id column
    op.add_column("chat_sessions", sa.Column("agent_run_id", sa.String(length=36), nullable=True))

    # Add judge_result_id column
    op.add_column(
        "chat_sessions", sa.Column("judge_result_id", sa.String(length=36), nullable=True)
    )

    # Migrate data: populate agent_run_id with the first element from agent_run_ids array
    op.execute(
        """
        UPDATE chat_sessions
        SET agent_run_id = agent_run_ids->>0
        WHERE jsonb_array_length(agent_run_ids) > 0
    """
    )

    # Clean up orphaned references that don't exist in agent_runs table
    op.execute(
        """
        UPDATE chat_sessions
        SET agent_run_id = NULL
        WHERE agent_run_id IS NOT NULL
        AND agent_run_id NOT IN (SELECT id FROM agent_runs)
    """
    )

    # Add foreign key constraint for agent_run_id
    op.create_foreign_key(
        "fk_chat_sessions_agent_run_id", "chat_sessions", "agent_runs", ["agent_run_id"], ["id"]
    )

    # Add foreign key constraint for judge_result_id
    op.create_foreign_key(
        "fk_chat_sessions_judge_result_id",
        "chat_sessions",
        "judge_results",
        ["judge_result_id"],
        ["id"],
    )

    # Add index for judge_result_id
    op.create_index("ix_chat_sessions_judge_result_id", "chat_sessions", ["judge_result_id"])


def downgrade() -> None:
    """Downgrade schema."""
    # Migrate data back: populate agent_run_ids array with current agent_run_id
    # (agent_run_ids column still exists since we didn't drop it in upgrade)
    op.execute(
        """
        UPDATE chat_sessions
        SET agent_run_ids = CASE
            WHEN agent_run_id IS NOT NULL THEN jsonb_build_array(agent_run_id)
            ELSE '[]'::jsonb
        END
    """
    )

    # Drop index for judge_result_id
    op.drop_index("ix_chat_sessions_judge_result_id", table_name="chat_sessions")

    # Drop foreign key constraints
    op.drop_constraint("fk_chat_sessions_judge_result_id", "chat_sessions", type_="foreignkey")
    op.drop_constraint("fk_chat_sessions_agent_run_id", "chat_sessions", type_="foreignkey")

    # Drop the new columns
    op.drop_column("chat_sessions", "judge_result_id")
    op.drop_column("chat_sessions", "agent_run_id")

    # Revert agent_run_ids column back to non-nullable
    op.alter_column("chat_sessions", "agent_run_ids", nullable=False)
