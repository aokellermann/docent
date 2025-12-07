# autoflake: skip_file
# pyright: ignore

# %%

import IPython

IPython.get_ipython().run_line_magic("load_ext", "autoreload")  # type: ignore
IPython.get_ipython().run_line_magic("autoreload", "2")  # type: ignore

# %%

from docent import Docent
from docent.data_models.formatted_objects import FormattedAgentRun, FormattedTranscript
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
    tg.name = 'Generating Agentic Forecast' AND
    (
        a.metadata_json ->> 'experiment_id' = 'mengk_kalshi_liquid_113025_20_12_37' OR
        a.metadata_json ->> 'experiment_id' = 'mengk_kalshi_liquid_112925_20_34_53'
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

# Join with the foreknowledge judge
rubric_id = "048d4801-9397-4a9b-9c8c-14b0368659f3"
df_foreknowledge = dc.dql_result_to_df_experimental(
    dc.execute_dql(
        cid,
        f"""
SELECT
    a.id AS agent_run_id,
    j.id AS judge_result_id,
    j.output ->> 'label' AS foreknowledge_label
FROM agent_runs a
JOIN judge_results j ON a.id = j.agent_run_id
WHERE
    j.rubric_id = '{rubric_id}' AND
    j.rubric_version = 5
""",
    )
)
df_foreknowledge["has_foreknowledge"] = (
    df_foreknowledge["foreknowledge_label"] == "foreknowledge"
) | (df_foreknowledge["foreknowledge_label"] == "wrong cutoff")
df_foreknowledge = df_foreknowledge.drop(columns=["foreknowledge_label"])
df = df.merge(df_foreknowledge, on="agent_run_id", how="inner")

# df = df[df["has_foreknowledge"] == False]

df


# %%

###########
# Helpers #
###########

# Configurable grouping columns - change this list to group by different dimensions
GROUP_BY_COLS = ["llm", "experiment_id", "has_foreknowledge"]
# Get unique combinations of grouping columns
unique_combos = df[GROUP_BY_COLS].drop_duplicates().sort_values(by=GROUP_BY_COLS)


# Helper function to create mask for filtering by group values
def make_group_mask(df: pd.DataFrame, group_values: dict) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for col, val in group_values.items():
        mask &= df[col] == val
    return mask


# Helper function to create config label from group values
def make_config_label(group_values: dict, sep: str = "\n") -> str:
    return sep.join(str(v) for v in group_values.values())


# %%

import matplotlib.pyplot as plt
import numpy as np

# Calculate mean accuracies and brier scores for each unique combo
accuracy_data = []
for _, row in unique_combos.iterrows():
    group_values = row.to_dict()
    mask = make_group_mask(df, group_values)
    group_df = df[mask]

    accuracy_data.append(
        {
            "label": make_config_label(group_values, sep=" / "),
            "mean_indep_accuracy": group_df["mean_indep_accuracy"].mean(),
            "consistency_accuracy": group_df["consistency_accuracy"].mean(),
            "scaled_accuracy": group_df["scaled_accuracy"].mean(),
            "mean_indep_brier": group_df["mean_indep_brier_score"].mean(),
            "consistency_brier": group_df["consistency_brier_score"].mean(),
            "scaled_brier": group_df["scaled_brier_score"].mean(),
        }
    )

# Create bar chart with two subplots
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

x = np.arange(len(accuracy_data))
width = 0.25

labels = [d["label"] for d in accuracy_data]
mean_indep_acc = [d["mean_indep_accuracy"] for d in accuracy_data]
consistency_acc = [d["consistency_accuracy"] for d in accuracy_data]
scaled_acc = [d["scaled_accuracy"] for d in accuracy_data]

mean_indep_brier = [d["mean_indep_brier"] for d in accuracy_data]
consistency_brier = [d["consistency_brier"] for d in accuracy_data]
scaled_brier = [d["scaled_brier"] for d in accuracy_data]

# Accuracy subplot
bars1 = ax1.bar(x - width, mean_indep_acc, width, label="Mean Indep")
bars2 = ax1.bar(x, consistency_acc, width, label="Consistency")
bars3 = ax1.bar(x + width, scaled_acc, width, label="Scaled")

for bar in bars1:
    height = bar.get_height()
    ax1.annotate(
        f"{height:.2f}",
        xy=(bar.get_x() + bar.get_width() / 2, height),
        xytext=(0, 3),
        textcoords="offset points",
        ha="center",
        va="bottom",
        fontsize=8,
    )

for bar in bars2:
    height = bar.get_height()
    ax1.annotate(
        f"{height:.2f}",
        xy=(bar.get_x() + bar.get_width() / 2, height),
        xytext=(0, 3),
        textcoords="offset points",
        ha="center",
        va="bottom",
        fontsize=8,
    )

for bar in bars3:
    height = bar.get_height()
    ax1.annotate(
        f"{height:.2f}",
        xy=(bar.get_x() + bar.get_width() / 2, height),
        xytext=(0, 3),
        textcoords="offset points",
        ha="center",
        va="bottom",
        fontsize=8,
    )

ax1.set_xlabel("Configuration")
ax1.set_ylabel("Accuracy")
ax1.set_title("Accuracy Comparison by Configuration")
ax1.set_xticks(x)
ax1.set_xticklabels(labels, rotation=45, ha="right")
ax1.legend()
ax1.set_ylim(0, 1)

# Brier score subplot
bars4 = ax2.bar(x - width, mean_indep_brier, width, label="Mean Indep")
bars5 = ax2.bar(x, consistency_brier, width, label="Consistency")
bars6 = ax2.bar(x + width, scaled_brier, width, label="Scaled")

for bar in bars4:
    height = bar.get_height()
    ax2.annotate(
        f"{height:.3f}",
        xy=(bar.get_x() + bar.get_width() / 2, height),
        xytext=(0, 3),
        textcoords="offset points",
        ha="center",
        va="bottom",
        fontsize=8,
    )

for bar in bars5:
    height = bar.get_height()
    ax2.annotate(
        f"{height:.3f}",
        xy=(bar.get_x() + bar.get_width() / 2, height),
        xytext=(0, 3),
        textcoords="offset points",
        ha="center",
        va="bottom",
        fontsize=8,
    )

for bar in bars6:
    height = bar.get_height()
    ax2.annotate(
        f"{height:.3f}",
        xy=(bar.get_x() + bar.get_width() / 2, height),
        xytext=(0, 3),
        textcoords="offset points",
        ha="center",
        va="bottom",
        fontsize=8,
    )

ax2.set_xlabel("Configuration")
ax2.set_ylabel("Brier Score (lower is better)")
ax2.set_title("Brier Score Comparison by Configuration")
ax2.set_xticks(x)
ax2.set_xticklabels(labels, rotation=45, ha="right")
ax2.legend()

plt.tight_layout()
plt.show()

# %%


for _, row in df[
    (df["experiment_id"] == "mengk_kalshi_liquid_113025_20_12_37")
    & (df["has_foreknowledge"] == False)
    & (df["scaled_accuracy"] == False)
].iterrows():
    arid = row["agent_run_id"]
    dc.tag_transcript(cid, arid, "incorrect_no-fk")

# %%
