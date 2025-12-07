# autoflake: skip_file
# pyright: ignore

# %%

import IPython

IPython.get_ipython().run_line_magic("load_ext", "autoreload")  # type: ignore
IPython.get_ipython().run_line_magic("autoreload", "2")  # type: ignore

# %%

from docent import Docent
from docent.sdk.llm_context import LLMContext
from docent_core._env_util import ENV

DOCENT_API_KEY = ENV.get("DOCENT_API_KEY")
DOCENT_DOMAIN = ENV.get("DOCENT_DOMAIN")
if not DOCENT_DOMAIN or not DOCENT_API_KEY:
    raise ValueError("DOCENT_API_KEY and DOCENT_DOMAIN must be set")
dc = Docent(api_key=DOCENT_API_KEY, domain=DOCENT_DOMAIN)

# %%

import pandas as pd
from tqdm.auto import tqdm

pd.set_option("display.float_format", "{:.3f}".format)

cid = "1f80cbbe-3b82-45db-9570-eb20346fe200"
df = dc.dql_result_to_df_experimental(
    dc.execute_dql(
        cid,
        """
SELECT
    a.id AS agent_run_id,
    a.metadata_json ->> 'experiment_id' AS experiment_id,
    a.metadata_json ->> 'base_llm_name' AS llm,
    a.metadata_json ->> 'llm_reasoning_effort' AS reasoning_effort,
    a.metadata_json ->> 'llm_verbosity' AS verbosity,
    a.metadata_json ->> 'pre_platt_scaling_probability' AS consistency_prob,
    a.metadata_json ->> 'post_platt_scaling_probability' AS scaled_prob,
    a.metadata_json ->> 'resolved_to' AS gold_prob,
    a.metadata_json ->> 'question' AS question,
    ARRAY_AGG(tg.metadata_json ->> 'post_calibration_probability') AS indep_probs
FROM agent_runs a
JOIN transcript_groups tg ON a.id = tg.agent_run_id
WHERE
    tg.name = 'Generating Agentic Forecast'
    AND (
        a.metadata_json ->> 'experiment_id' = 'mengk_kalshi_liquid_113025_20_12_37'
        -- OR a.metadata_json ->> 'experiment_id' = 'mengk_kalshi_liquid_112925_20_34_53'
        -- OR a.metadata_json ->> 'experiment_id' = 'mengk_kalshi_liquid_112925_20_35_08'
    )
GROUP BY
    a.id,
    a.metadata_json ->> 'experiment_id',
    a.metadata_json ->> 'base_llm_name',
    a.metadata_json ->> 'llm_reasoning_effort',
    a.metadata_json ->> 'llm_verbosity',
    a.metadata_json ->> 'pre_platt_scaling_probability',
    a.metadata_json ->> 'post_platt_scaling_probability',
    a.metadata_json ->> 'resolved_to',
    a.metadata_json ->> 'question'
""",
    )
)
rows_before = len(df)
df = df.dropna()
rows_after = len(df)
print(f"Dropped {rows_before - rows_after} rows (from {rows_before} to {rows_after})")


def _f(x: list[str | None]):
    filtered = [float(v) for v in x if v is not None]
    return sum(filtered) / len(filtered) if filtered else None


df["mean_indep_prob"] = df["indep_probs"].apply(_f)

df["scaled_brier_score"] = (df["scaled_prob"] - df["gold_prob"]) ** 2
df["mean_indep_brier_score"] = (df["mean_indep_prob"] - df["gold_prob"]) ** 2
df["consistency_brier_score"] = (df["consistency_prob"] - df["gold_prob"]) ** 2
df["scaled_accuracy"] = ((df["scaled_prob"] >= 0.5) & (df["gold_prob"] >= 0.5)) | (
    (df["scaled_prob"] < 0.5) & (df["gold_prob"] < 0.5)
)
df["mean_indep_accuracy"] = ((df["mean_indep_prob"] >= 0.5) & (df["gold_prob"] >= 0.5)) | (
    (df["mean_indep_prob"] < 0.5) & (df["gold_prob"] < 0.5)
)
df["consistency_accuracy"] = ((df["consistency_prob"] >= 0.5) & (df["gold_prob"] >= 0.5)) | (
    (df["consistency_prob"] < 0.5) & (df["gold_prob"] < 0.5)
)

df = df[
    [
        "agent_run_id",
        "experiment_id",
        "llm",
        "reasoning_effort",
        "verbosity",
        "question",
        "mean_indep_prob",
        "consistency_prob",
        "scaled_prob",
        "gold_prob",
        "scaled_brier_score",
        "mean_indep_brier_score",
        "consistency_brier_score",
        "scaled_accuracy",
        "mean_indep_accuracy",
        "consistency_accuracy",
        "indep_probs",
    ]
]
df = df.sort_values(by="scaled_brier_score", ascending=False)
df

# %%

# Get a few agent runs
agent_runs = [dc.get_agent_run(cid, arid) for arid in tqdm(df.head(1)["agent_run_id"].tolist())]

# %%

from docent.data_models.agent_run import AgentRunView, SelectionSpec

for ar in agent_runs:
    if ar is None:
        print("warn: agent run is None")
        continue

    # dc.open_agent_run(cid, ar.id)

    # print(ar.to_text_new(indent=2, full_tree=True))
    from pprint import pprint

    # c_tree = ar.get_canonical_tree(full_tree=True)
    # pprint(c_tree)
    # for id, node in c_tree.items():
    #     if len(node.children_ids) != len(set(node.children_ids)):
    #         raise ValueError(f"warn: duplicate children_ids for node {id}")
    # print(ar.to_text_new(indent=2, full_tree=True))
    ar_view = AgentRunView.from_agent_run(ar)
    ar_view.set_node_selection("__global_root", False)
    ar_view.set_node_selection("63411ca1-2f48-4abc-874e-46b076a9aec5", True)
    ar_view.set_node_selection("26ba20ad-0e45-4e6b-922b-487e59c5476f", False)
    # ar_view.set_metadata_selection("26ba20ad-0e45-4e6b-922b-487e59c5476f", True)
    print(ar_view.to_text(indent=2, full_tree=False))

    #     # Determine which transcript groups we want to run over separately
    #     # That is, each of the independent forecast runs
    #     result = dc.execute_dql(
    #         cid,
    #         f"""
    # SELECT tg.id AS transcript_group_id
    # FROM transcript_groups tg
    # WHERE tg.agent_run_id = '{ar.id}' AND tg.name = 'Generating Agentic Forecast'
    # """,
    #     )
    #     tg_ids = [row[0] for row in result["rows"]]
    #     for tg_id in tg_ids:
    #         formatted_ar = FormattedAgentRun.from_agent_run(ar)
    #         formatted_ar.only_keep_transcript_group_subtrees([tg_id])
    #         print("===\n", formatted_ar.to_text_new(indent=2), "\n===", sep="")

    break

"""
Things to continue thinking about:
- I should also be able to apply the selection spec to the canonical tree. Right now, there's not really a method for that.
- It still sort of bothers me that the selection spec has a circular relationship with the agent run.
  - It does seem sensible to pull the canonical tree and to underscore text underscore new method into another agent run view object which then also manages the selection spec. This would just require some gentle refactoring to convert all the two-text new methods to wrap an agent run view. Seems fine though.
- I wonder how hard it would be to integrate this into things full-stack.
"""

# %%

ar_view._spec.nodes
# %%
