"""prod to main

Revision ID: 6d9be98a2750
Revises:
Create Date: 2025-07-21 13:25:41.390894

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6d9be98a2750"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "diff_queries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("collection_id", sa.String(length=36), nullable=False),
        sa.Column("grouping_md_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("md_field_value_1", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("md_field_value_2", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("focus", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["collections.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_diff_queries_collection_id"), "diff_queries", ["collection_id"], unique=False
    )
    op.create_table(
        "rubrics",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("collection_id", sa.String(length=36), nullable=False),
        sa.Column("high_level_description", sa.Text(), nullable=False),
        sa.Column("inclusion_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("exclusion_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["collections.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_rubrics_collection_id"), "rubrics", ["collection_id"], unique=False)
    op.create_table(
        "charts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("view_id", sa.String(length=36), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("series_key", sa.Text(), nullable=True),
        sa.Column("x_key", sa.Text(), nullable=True),
        sa.Column("y_key", sa.Text(), nullable=True),
        sa.Column("sql_query", sa.Text(), nullable=True),
        sa.Column("chart_type", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["view_id"],
            ["views.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_charts_created_by"), "charts", ["created_by"], unique=False)
    op.create_index(op.f("ix_charts_view_id"), "charts", ["view_id"], unique=False)
    op.create_table(
        "diff_claims_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("diff_query_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["diff_query_id"],
            ["diff_queries.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_diff_claims_results_diff_query_id"),
        "diff_claims_results",
        ["diff_query_id"],
        unique=False,
    )
    op.create_table(
        "diff_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("diff_query_id", sa.String(length=36), nullable=False),
        sa.Column("agent_run_1_id", sa.String(length=36), nullable=False),
        sa.Column("agent_run_2_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_run_1_id"],
            ["agent_runs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_2_id"],
            ["agent_runs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["diff_query_id"],
            ["diff_queries.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_diff_results_agent_run_1_id"), "diff_results", ["agent_run_1_id"], unique=False
    )
    op.create_index(
        op.f("ix_diff_results_agent_run_2_id"), "diff_results", ["agent_run_2_id"], unique=False
    )
    op.create_index(
        op.f("ix_diff_results_diff_query_id"), "diff_results", ["diff_query_id"], unique=False
    )
    op.create_table(
        "judge_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_run_id", sa.String(length=36), nullable=False),
        sa.Column("rubric_id", sa.String(length=36), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["rubric_id"],
            ["rubrics.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_judge_results_agent_run_id"), "judge_results", ["agent_run_id"], unique=False
    )
    op.create_index(
        op.f("ix_judge_results_rubric_id"), "judge_results", ["rubric_id"], unique=False
    )
    op.create_table(
        "rubric_centroids",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("collection_id", sa.String(length=36), nullable=False),
        sa.Column("rubric_id", sa.String(length=36), nullable=False),
        sa.Column("centroid", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["collections.id"],
        ),
        sa.ForeignKeyConstraint(
            ["rubric_id"],
            ["rubrics.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_rubric_centroids_collection_id"),
        "rubric_centroids",
        ["collection_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_rubric_centroids_rubric_id"), "rubric_centroids", ["rubric_id"], unique=False
    )
    op.create_table(
        "diff_instances",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("paired_diff_result_id", sa.String(length=36), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("shared_context", sa.Text(), nullable=False),
        sa.Column("agent_1_action", sa.Text(), nullable=False),
        sa.Column("agent_1_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("agent_2_action", sa.Text(), nullable=False),
        sa.Column("agent_2_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["paired_diff_result_id"],
            ["diff_results.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_diff_instances_paired_diff_result_id"),
        "diff_instances",
        ["paired_diff_result_id"],
        unique=False,
    )
    op.create_table(
        "judge_result_centroids",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("judge_result_id", sa.String(length=36), nullable=False),
        sa.Column("centroid_id", sa.String(length=36), nullable=False),
        sa.Column("decision", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["centroid_id"],
            ["rubric_centroids.id"],
        ),
        sa.ForeignKeyConstraint(
            ["judge_result_id"],
            ["judge_results.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("judge_result_id", "centroid_id", name="uq_judge_result_centroid"),
    )
    op.create_index(
        op.f("ix_judge_result_centroids_centroid_id"),
        "judge_result_centroids",
        ["centroid_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_judge_result_centroids_judge_result_id"),
        "judge_result_centroids",
        ["judge_result_id"],
        unique=False,
    )
    op.create_table(
        "paired_search_query",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("collection_id", sa.String(length=36), nullable=False),
        sa.Column("diff_claims_result_id", sa.String(length=36), nullable=True),
        sa.Column("grouping_md_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("md_field_value_1", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("md_field_value_2", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("action_1", sa.Text(), nullable=False),
        sa.Column("action_2", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["collections.id"],
        ),
        sa.ForeignKeyConstraint(
            ["diff_claims_result_id"],
            ["diff_claims_results.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_paired_search_query_collection_id"),
        "paired_search_query",
        ["collection_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_paired_search_query_diff_claims_result_id"),
        "paired_search_query",
        ["diff_claims_result_id"],
        unique=False,
    )
    op.create_table(
        "paired_search_result",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("paired_search_query_id", sa.String(length=36), nullable=False),
        sa.Column("agent_run_1_id", sa.String(length=36), nullable=False),
        sa.Column("agent_run_2_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_run_1_id"],
            ["agent_runs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_2_id"],
            ["agent_runs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["paired_search_query_id"],
            ["paired_search_query.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_paired_search_result_agent_run_1_id"),
        "paired_search_result",
        ["agent_run_1_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_paired_search_result_agent_run_2_id"),
        "paired_search_result",
        ["agent_run_2_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_paired_search_result_paired_search_query_id"),
        "paired_search_result",
        ["paired_search_query_id"],
        unique=False,
    )
    op.create_table(
        "paired_search_instance",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("paired_search_result_id", sa.String(length=36), nullable=False),
        sa.Column("shared_context", sa.Text(), nullable=False),
        sa.Column("agent_1_action_1", sa.Boolean(), nullable=False),
        sa.Column("agent_1_action_1_explanation", sa.Text(), nullable=True),
        sa.Column("agent_1_action_2", sa.Boolean(), nullable=False),
        sa.Column("agent_1_action_2_explanation", sa.Text(), nullable=True),
        sa.Column("agent_2_action_1", sa.Boolean(), nullable=False),
        sa.Column("agent_2_action_1_explanation", sa.Text(), nullable=True),
        sa.Column("agent_2_action_2", sa.Boolean(), nullable=False),
        sa.Column("agent_2_action_2_explanation", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["paired_search_result_id"],
            ["paired_search_result.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_paired_search_instance_paired_search_result_id"),
        "paired_search_instance",
        ["paired_search_result_id"],
        unique=False,
    )

    #######################
    # DESTRUCTIVE ACTIONS #
    #######################

    # All of these are for removing Sherwin's old diffing pipeline, I believe

    # Remove Sherwin's claims table
    op.drop_index(op.f("ix_claim_idx"), table_name="claim")
    op.drop_index(op.f("ix_claim_transcript_diff_id"), table_name="claim")
    op.drop_table("claim")

    # Remove Sherwin's transcript_diff table
    op.drop_index(op.f("ix_transcript_diff_agent_run_1_id"), table_name="transcript_diff")
    op.drop_index(op.f("ix_transcript_diff_agent_run_2_id"), table_name="transcript_diff")
    op.drop_index(op.f("ix_transcript_diff_collection_id"), table_name="transcript_diff")
    op.drop_index(op.f("ix_transcript_diff_diffs_report_id"), table_name="transcript_diff")
    op.drop_index(op.f("ix_transcript_diff_title"), table_name="transcript_diff")
    op.drop_table("transcript_diff")

    # Remove Sherwin's diff_attributes table
    op.drop_index(op.f("ix_diff_attributes_attribute"), table_name="diff_attributes")
    op.drop_index(op.f("ix_diff_attributes_attribute_idx"), table_name="diff_attributes")
    op.drop_index(op.f("ix_diff_attributes_collection_id"), table_name="diff_attributes")
    op.drop_index(op.f("ix_diff_attributes_data_id_1"), table_name="diff_attributes")
    op.drop_index(op.f("ix_diff_attributes_data_id_2"), table_name="diff_attributes")
    op.drop_table("diff_attributes")

    # Remove Sherwin's diffs_report table
    op.drop_index(op.f("ix_diffs_report_collection_id"), table_name="diffs_report")
    op.drop_table("diffs_report")


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "diffs_report",
        sa.Column("id", sa.VARCHAR(length=36), autoincrement=False, nullable=False),
        sa.Column("collection_id", sa.VARCHAR(length=36), autoincrement=False, nullable=False),
        sa.Column("name", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("experiment_id_1", sa.VARCHAR(length=36), autoincrement=False, nullable=False),
        sa.Column("experiment_id_2", sa.VARCHAR(length=36), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["collections.id"], name="diffs_report_collection_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id", name="diffs_report_pkey"),
        postgresql_ignore_search_path=False,
    )
    op.create_index(
        op.f("ix_diffs_report_collection_id"), "diffs_report", ["collection_id"], unique=False
    )
    op.create_table(
        "diff_attributes",
        sa.Column("id", sa.VARCHAR(length=36), autoincrement=False, nullable=False),
        sa.Column("collection_id", sa.VARCHAR(length=36), autoincrement=False, nullable=False),
        sa.Column("data_id_1", sa.VARCHAR(length=36), autoincrement=False, nullable=False),
        sa.Column("data_id_2", sa.VARCHAR(length=36), autoincrement=False, nullable=False),
        sa.Column("attribute", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("attribute_idx", sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column("claim", sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column("evidence", sa.TEXT(), autoincrement=False, nullable=True),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["collections.id"], name=op.f("diff_attributes_collection_id_fkey")
        ),
        sa.ForeignKeyConstraint(
            ["data_id_1"], ["agent_runs.id"], name=op.f("diff_attributes_data_id_1_fkey")
        ),
        sa.ForeignKeyConstraint(
            ["data_id_2"], ["agent_runs.id"], name=op.f("diff_attributes_data_id_2_fkey")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("diff_attributes_pkey")),
        sa.UniqueConstraint(
            "collection_id",
            "data_id_1",
            "data_id_2",
            "attribute",
            "attribute_idx",
            name=op.f("uq_diff_attribute_key_combination"),
            postgresql_include=[],
            postgresql_nulls_not_distinct=False,
        ),
    )
    op.create_index(
        op.f("ix_diff_attributes_data_id_2"), "diff_attributes", ["data_id_2"], unique=False
    )
    op.create_index(
        op.f("ix_diff_attributes_data_id_1"), "diff_attributes", ["data_id_1"], unique=False
    )
    op.create_index(
        op.f("ix_diff_attributes_collection_id"), "diff_attributes", ["collection_id"], unique=False
    )
    op.create_index(
        op.f("ix_diff_attributes_attribute_idx"), "diff_attributes", ["attribute_idx"], unique=False
    )
    op.create_index(
        op.f("ix_diff_attributes_attribute"), "diff_attributes", ["attribute"], unique=False
    )
    op.create_table(
        "transcript_diff",
        sa.Column("id", sa.VARCHAR(length=36), autoincrement=False, nullable=False),
        sa.Column("collection_id", sa.VARCHAR(length=36), autoincrement=False, nullable=False),
        sa.Column("diffs_report_id", sa.VARCHAR(length=36), autoincrement=False, nullable=False),
        sa.Column("agent_run_1_id", sa.VARCHAR(length=36), autoincrement=False, nullable=False),
        sa.Column("agent_run_2_id", sa.VARCHAR(length=36), autoincrement=False, nullable=False),
        sa.Column("title", sa.TEXT(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_run_1_id"], ["agent_runs.id"], name="transcript_diff_agent_run_1_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_2_id"], ["agent_runs.id"], name="transcript_diff_agent_run_2_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["collections.id"], name="transcript_diff_collection_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["diffs_report_id"], ["diffs_report.id"], name="transcript_diff_diffs_report_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id", name="transcript_diff_pkey"),
        sa.UniqueConstraint(
            "collection_id",
            "diffs_report_id",
            "agent_run_1_id",
            "agent_run_2_id",
            name="uq_transcript_diff_key_combination",
            postgresql_include=[],
            postgresql_nulls_not_distinct=False,
        ),
        postgresql_ignore_search_path=False,
    )
    op.create_index(op.f("ix_transcript_diff_title"), "transcript_diff", ["title"], unique=False)
    op.create_index(
        op.f("ix_transcript_diff_diffs_report_id"),
        "transcript_diff",
        ["diffs_report_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transcript_diff_collection_id"), "transcript_diff", ["collection_id"], unique=False
    )
    op.create_index(
        op.f("ix_transcript_diff_agent_run_2_id"),
        "transcript_diff",
        ["agent_run_2_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transcript_diff_agent_run_1_id"),
        "transcript_diff",
        ["agent_run_1_id"],
        unique=False,
    )
    op.create_table(
        "claim",
        sa.Column("id", sa.VARCHAR(length=36), autoincrement=False, nullable=False),
        sa.Column("transcript_diff_id", sa.VARCHAR(length=36), autoincrement=False, nullable=False),
        sa.Column("idx", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("claim_summary", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("shared_context", sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column("agent_1_action", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("agent_2_action", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("evidence", sa.TEXT(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["transcript_diff_id"],
            ["transcript_diff.id"],
            name=op.f("claim_transcript_diff_id_fkey"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("claim_pkey")),
    )
    op.create_index(
        op.f("ix_claim_transcript_diff_id"), "claim", ["transcript_diff_id"], unique=False
    )
    op.create_index(op.f("ix_claim_idx"), "claim", ["idx"], unique=False)
    op.drop_index(
        op.f("ix_paired_search_instance_paired_search_result_id"),
        table_name="paired_search_instance",
    )
    op.drop_table("paired_search_instance")
    op.drop_index(
        op.f("ix_paired_search_result_paired_search_query_id"), table_name="paired_search_result"
    )
    op.drop_index(op.f("ix_paired_search_result_agent_run_2_id"), table_name="paired_search_result")
    op.drop_index(op.f("ix_paired_search_result_agent_run_1_id"), table_name="paired_search_result")
    op.drop_table("paired_search_result")
    op.drop_index(
        op.f("ix_paired_search_query_diff_claims_result_id"), table_name="paired_search_query"
    )
    op.drop_index(op.f("ix_paired_search_query_collection_id"), table_name="paired_search_query")
    op.drop_table("paired_search_query")
    op.drop_index(
        op.f("ix_judge_result_centroids_judge_result_id"), table_name="judge_result_centroids"
    )
    op.drop_index(
        op.f("ix_judge_result_centroids_centroid_id"), table_name="judge_result_centroids"
    )
    op.drop_table("judge_result_centroids")
    op.drop_index(op.f("ix_diff_instances_paired_diff_result_id"), table_name="diff_instances")
    op.drop_table("diff_instances")
    op.drop_index(op.f("ix_rubric_centroids_rubric_id"), table_name="rubric_centroids")
    op.drop_index(op.f("ix_rubric_centroids_collection_id"), table_name="rubric_centroids")
    op.drop_table("rubric_centroids")
    op.drop_index(op.f("ix_judge_results_rubric_id"), table_name="judge_results")
    op.drop_index(op.f("ix_judge_results_agent_run_id"), table_name="judge_results")
    op.drop_table("judge_results")
    op.drop_index(op.f("ix_diff_results_diff_query_id"), table_name="diff_results")
    op.drop_index(op.f("ix_diff_results_agent_run_2_id"), table_name="diff_results")
    op.drop_index(op.f("ix_diff_results_agent_run_1_id"), table_name="diff_results")
    op.drop_table("diff_results")
    op.drop_index(op.f("ix_diff_claims_results_diff_query_id"), table_name="diff_claims_results")
    op.drop_table("diff_claims_results")
    op.drop_index(op.f("ix_charts_view_id"), table_name="charts")
    op.drop_index(op.f("ix_charts_created_by"), table_name="charts")
    op.drop_table("charts")
    op.drop_index(op.f("ix_rubrics_collection_id"), table_name="rubrics")
    op.drop_table("rubrics")
    op.drop_index(op.f("ix_diff_queries_collection_id"), table_name="diff_queries")
    op.drop_table("diff_queries")
    # ### end Alembic commands ###
