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
        a.metadata_json ->> 'experiment_id' = 'mengk_kalshi_liquid_112925_20_34_53' OR
        a.metadata_json ->> 'experiment_id' = 'mengk_kalshi_liquid_112925_20_35_08'
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

df = df[df["has_foreknowledge"] == False]

df

# %%

for _, row in df[
    (df["experiment_id"] == "mengk_kalshi_liquid_113025_20_12_37")
    & (df["has_foreknowledge"] == False)
].iterrows():
    arid = row["agent_run_id"]
    dc.tag_transcript(cid, arid, "new-exp_no-fk")

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

############################
# Basic summary statistics #
############################

# %%

# Plot accuracy and brier score by (llm, reasoning_effort, verbosity) combination
import matplotlib.pyplot as plt
import numpy as np

# Collect data for plotting
plot_data = []
for _, row in unique_combos.iterrows():
    group_values = {col: row[col] for col in GROUP_BY_COLS}
    mask = make_group_mask(df, group_values)
    df_filtered = df[mask]

    mean_scaled_accuracy = df_filtered["scaled_accuracy"].mean()
    mean_scaled_brier = df_filtered["scaled_brier_score"].mean()
    mean_indep_accuracy = df_filtered["mean_indep_accuracy"].mean()
    mean_indep_brier = df_filtered["mean_indep_brier_score"].mean()
    mean_consistency_accuracy = df_filtered["consistency_accuracy"].mean()
    mean_consistency_brier = df_filtered["consistency_brier_score"].mean()

    plot_data.append(
        {
            "config": make_config_label(group_values),
            "scaled_accuracy": mean_scaled_accuracy,
            "scaled_brier_score": mean_scaled_brier,
            "mean_indep_accuracy": mean_indep_accuracy,
            "mean_indep_brier_score": mean_indep_brier,
            "consistency_accuracy": mean_consistency_accuracy,
            "consistency_brier_score": mean_consistency_brier,
        }
    )

# Create bar charts
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

configs = [d["config"] for d in plot_data]
x = np.arange(len(configs))
width = 0.25  # Width of bars

# Accuracy bar chart (mean_indep, consistency, and scaled)
mean_indep_accuracies = [d["mean_indep_accuracy"] for d in plot_data]
consistency_accuracies = [d["consistency_accuracy"] for d in plot_data]
scaled_accuracies = [d["scaled_accuracy"] for d in plot_data]
bars1_1 = ax1.bar(x - width, mean_indep_accuracies, width, alpha=0.8, label="Mean Independent")
bars1_2 = ax1.bar(x, consistency_accuracies, width, alpha=0.8, label="Consistency")
bars1_3 = ax1.bar(x + width, scaled_accuracies, width, alpha=0.8, label="Scaled")

# Add value labels on top of bars
for bars in [bars1_1, bars1_2, bars1_3]:
    for bar in bars:
        height = bar.get_height()
        ax1.annotate(
            f"{height:.2f}",
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 3),  # 3 points vertical offset
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
        )

ax1.set_xlabel("Model Configuration")
ax1.set_ylabel("consistency_accuracy")
ax1.set_title("Accuracy by Model Configuration")
ax1.set_xticks(x)
ax1.set_xticklabels(configs, rotation=45, ha="right")
ax1.grid(True, alpha=0.3, axis="y")
ax1.legend()

# Brier score bar chart (mean_indep, consistency, and scaled)
mean_indep_brier_scores = [d["mean_indep_brier_score"] for d in plot_data]
consistency_brier_scores = [d["consistency_brier_score"] for d in plot_data]
scaled_brier_scores = [d["scaled_brier_score"] for d in plot_data]
bars2_1 = ax2.bar(
    x - width, mean_indep_brier_scores, width, alpha=0.8, color="orange", label="Mean Independent"
)
bars2_2 = ax2.bar(
    x, consistency_brier_scores, width, alpha=0.8, color="darkorange", label="Consistency"
)
bars2_3 = ax2.bar(x + width, scaled_brier_scores, width, alpha=0.8, color="red", label="Scaled")

# Add value labels on top of bars
for bars in [bars2_1, bars2_2, bars2_3]:
    for bar in bars:
        height = bar.get_height()
        ax2.annotate(
            f"{height:.2f}",
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 3),  # 3 points vertical offset
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
        )

ax2.set_xlabel("Model Configuration")
ax2.set_ylabel("Brier Score")
ax2.set_title("Brier Score by Model Configuration")
ax2.set_xticks(x)
ax2.set_xticklabels(configs, rotation=45, ha="right")
ax2.grid(True, alpha=0.3, axis="y")
ax2.legend()

plt.tight_layout()
plt.show()

# %%

#################
# Foreknowledge #
#################

# # Examine foreknowledge more carefully; when it happens, why are things incorrect?
# df_foreknowledge_wrong = df[df["has_foreknowledge"] & (df["scaled_accuracy"] == False)]
# row = df_foreknowledge_wrong.iloc[3]
# dc.open_rubric(cid, rubric_id, row["agent_run_id"], row["judge_result_id"])

# # Are some questions more prone to foreknowledge than others
# foreknowledge_by_question = (
#     df.groupby("question")
#     .agg(
#         total=("has_foreknowledge", "count"),
#         foreknowledge_count=("has_foreknowledge", "sum"),
#     )
#     .reset_index()
# )
# foreknowledge_by_question["foreknowledge_fraction"] = (
#     foreknowledge_by_question["foreknowledge_count"] / foreknowledge_by_question["total"]
# )
# foreknowledge_by_question = foreknowledge_by_question.sort_values(
#     by="foreknowledge_fraction", ascending=False
# )

# # Histogram of foreknowledge fraction by question
# plt.figure(figsize=(10, 6))
# plt.hist(foreknowledge_by_question["foreknowledge_fraction"], bins=20, edgecolor="black", alpha=0.7)
# plt.xlabel("Foreknowledge Fraction")
# plt.ylabel("Number of Questions")
# plt.title("Distribution of Foreknowledge Fraction Across Questions")
# plt.grid(True, alpha=0.3, axis="y")
# plt.tight_layout()
# plt.show()

# %%

#########################################################################################
# Explain diffs between models                                                          #
# Find questions where models (on average) do substantively differently from each other #
#########################################################################################

# %%

# Group by (grouping cols + question) and aggregate brier scores and accuracies
grouped_df = (
    df.groupby(GROUP_BY_COLS + ["question"])
    .agg({"scaled_brier_score": list, "agent_run_id": list})
    .reset_index()
)

# Create pivot tables for average scaled brier score and accuracy by question and grouping columns
import numpy as np

# Create a combined column for grouping columns
df["model_config"] = (
    df[GROUP_BY_COLS].astype(str).agg("_".join, axis=1)
)  # Note: uses "_" for column names

# Pivot table for average scaled brier score with count
brier_pivot_mean = df.pivot_table(
    values="scaled_brier_score", index="question", columns="model_config", aggfunc="mean"
)
brier_pivot_count = df.pivot_table(
    values="scaled_brier_score", index="question", columns="model_config", aggfunc="count"
)
# Pivot table for agent_run_ids (aggregated as list)
brier_pivot_ids = df.pivot_table(
    values="agent_run_id", index="question", columns="model_config", aggfunc=list
)

# Combine mean and count into a single display
brier_pivot = brier_pivot_mean.copy()
for col in brier_pivot.columns:
    brier_pivot[col] = (
        brier_pivot_mean[col].apply(lambda x: f"{x:.3f}")
        + " (n="
        + brier_pivot_count[col].astype(str)
        + ")"
    )

# Sort by variance across model configurations (using the mean values)
brier_pivot_mean["variance"] = brier_pivot_mean.var(axis=1)
sorted_index = brier_pivot_mean.sort_values(by="variance", ascending=False).index
brier_pivot = brier_pivot.loc[sorted_index]
brier_pivot_ids = brier_pivot_ids.loc[sorted_index]

brier_pivot.head(10)

# %%

##############################################
# WTF is going on with consistency analysis? #
##############################################

# %%

# Create separate scatterplots of pre_brier vs post_brier for each grouping column combination
import matplotlib.pyplot as plt

num_combos = len(unique_combos)
cols = 3
rows = (num_combos + cols - 1) // cols  # Calculate rows needed

fig, axes = plt.subplots(rows, cols, figsize=(15, 5 * rows))
axes = axes.flatten() if num_combos > 1 else [axes]

for idx, (_, row) in enumerate(unique_combos.iterrows()):
    group_values = {col: row[col] for col in GROUP_BY_COLS}
    mask = make_group_mask(df, group_values)
    df_filtered = df[mask]

    # Calculate average brier scores
    avg_pre_brier = df_filtered["mean_indep_brier_score"].mean()
    avg_post_brier = df_filtered["consistency_brier_score"].mean()
    avg_diff = avg_post_brier - avg_pre_brier

    ax = axes[idx]

    # Add shaded regions to show good/bad quadrants
    # Green: pre > 0.25 and post < 0.25 (lower right quadrant - good)
    ax.axhspan(0, 0.25, xmin=0.25, xmax=1, alpha=0.1, color="green", zorder=0)
    # Red: pre < 0.25 and post > 0.25 (upper left quadrant - bad)
    ax.axhspan(0.25, 1, xmin=0, xmax=0.25, alpha=0.1, color="red", zorder=0)

    # Add reference lines at 0.25
    ax.axhline(y=0.25, color="gray", linestyle=":", alpha=0.5, linewidth=1)
    ax.axvline(x=0.25, color="gray", linestyle=":", alpha=0.5, linewidth=1)

    ax.scatter(
        df_filtered["mean_indep_brier_score"],
        df_filtered["consistency_brier_score"],
        alpha=0.4,
        zorder=2,
    )

    # Add diagonal line (where pre = post)
    min_val = min(
        df_filtered["mean_indep_brier_score"].min(), df_filtered["consistency_brier_score"].min()
    )
    max_val = max(
        df_filtered["mean_indep_brier_score"].max(), df_filtered["consistency_brier_score"].max()
    )
    ax.plot([min_val, max_val], [min_val, max_val], "r--", alpha=0.5, label="x=y", zorder=1)

    ax.set_xlabel("Pre-Brier Score")
    ax.set_ylabel("Post-Brier Score")
    config_title = ", ".join(str(v) for v in group_values.values())
    ax.set_title(f"{config_title}\n(n={len(df_filtered)})\nΔ={avg_diff:.4f}")
    ax.grid(True, alpha=0.3)
    ax.legend()

# Hide any unused subplots
for idx in range(num_combos, len(axes)):
    axes[idx].set_visible(False)

plt.tight_layout()
plt.show()

# %%

# Create confusion matrix-style visualizations for accuracy
import numpy as np
from matplotlib import colors

fig, axes = plt.subplots(rows, cols, figsize=(15, 5 * rows))
axes = axes.flatten() if num_combos > 1 else [axes]

for idx, (_, row) in enumerate(unique_combos.iterrows()):
    group_values = {col: row[col] for col in GROUP_BY_COLS}
    mask = make_group_mask(df, group_values)
    df_filtered = df[mask]

    # Create confusion matrix: rows = post_accuracy, cols = pre_accuracy
    # Row 0 = Post Correct, Row 1 = Post Incorrect
    confusion = np.zeros((2, 2))
    confusion[0, 0] = (
        (df_filtered["mean_indep_accuracy"] == False)
        & (df_filtered["consistency_accuracy"] == True)
    ).sum()  # Pre incorrect, Post correct
    confusion[0, 1] = (
        (df_filtered["mean_indep_accuracy"] == True) & (df_filtered["consistency_accuracy"] == True)
    ).sum()  # Both correct
    confusion[1, 0] = (
        (df_filtered["mean_indep_accuracy"] == False)
        & (df_filtered["consistency_accuracy"] == False)
    ).sum()  # Both incorrect
    confusion[1, 1] = (
        (df_filtered["mean_indep_accuracy"] == True)
        & (df_filtered["consistency_accuracy"] == False)
    ).sum()  # Pre correct, Post incorrect

    # Calculate percentage changes
    total = len(df_filtered)
    avg_pre_acc = df_filtered["mean_indep_accuracy"].mean()
    avg_post_acc = df_filtered["consistency_accuracy"].mean()
    acc_diff = avg_post_acc - avg_pre_acc

    ax = axes[idx]

    # Create heatmap
    im = ax.imshow(confusion, cmap="Blues", aspect="auto")

    # Set ticks and labels
    ax.set_xticks([0, 1])
    ax.set_yticks([0, 1])
    ax.set_xticklabels(["Pre Incorrect", "Pre Correct"])
    ax.set_yticklabels(["Post Correct", "Post Incorrect"])
    ax.set_xlabel("Pre-Calibration Accuracy")
    ax.set_ylabel("Post-Calibration Accuracy")

    # Add text annotations with counts and percentages
    for i in range(2):
        for j in range(2):
            count = int(confusion[i, j])
            pct = confusion[i, j] / total * 100
            text = ax.text(
                j,
                i,
                f"{count}\n({pct:.1f}%)",
                ha="center",
                va="center",
                color="black" if confusion[i, j] < confusion.max() / 2 else "white",
                fontsize=12,
                weight="bold",
            )

    # Add colorbar
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    config_title = ", ".join(str(v) for v in group_values.values())
    ax.set_title(f"{config_title}\n(n={total})\nΔAcc={acc_diff:.4f}")

# Hide any unused subplots
for idx in range(num_combos, len(axes)):
    axes[idx].set_visible(False)

plt.tight_layout()
plt.show()

# %%

# Tag runs with consistency_hurt or consistency_helped
consistency_hurt = df[
    (df["mean_indep_brier_score"] < 0.25) & (df["consistency_brier_score"] > 0.25)
]
for ar_id in tqdm(consistency_hurt["agent_run_id"].tolist()):
    try:
        dc.tag_transcript(cid, ar_id, "consistency_hurt")
    except Exception as e:
        if (
            hasattr(e, "response")
            and hasattr(e.response, "status_code")
            and e.response.status_code == 409
        ):
            print(f"Tag already exists for {ar_id}")
            continue
        raise
consistency_helped = df[
    (df["mean_indep_brier_score"] > 0.25) & (df["consistency_brier_score"] < 0.25)
]
for ar_id in tqdm(consistency_helped["agent_run_id"].tolist()):
    try:
        dc.tag_transcript(cid, ar_id, "consistency_helped")
    except Exception as e:
        if (
            hasattr(e, "response")
            and hasattr(e.response, "status_code")
            and e.response.status_code == 409
        ):
            print(f"Tag already exists for {ar_id}")
            continue
        raise

# %%

#####################
# Manual commenting #
#####################

import docent.trace as dt

dt.initialize_tracing(collection_id=cid, endpoint=f"https://api.{DOCENT_DOMAIN}/rest/telemetry")

with dt.agent_run_context(agent_run_id="6fdfe619-7368-4cf3-80d7-a97bf54a4a28"):
    dt.agent_run_metadata(
        metadata={
            "mengk_comments": """
Yet another example of the correct answer being in the context window but the agent completely ignoring it. It seems like o3 actually tries not to cheat?!
""".strip()
        }
    )

# %%

rows = dc.dql_result_to_dicts(
    dc.execute_dql(
        cid,
        """
SELECT
    a.id AS agent_run_id,
    a.metadata_json ->> 'mengk_comments' AS mengk_comments
FROM agent_runs a
WHERE a.metadata_json ->> 'mengk_comments' IS NOT NULL
""",
    )
)
rows

# %%
