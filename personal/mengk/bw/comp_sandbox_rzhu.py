# autoflake: skip_file
# pyright: ignore

# %%

import IPython

IPython.get_ipython().run_line_magic("load_ext", "autoreload")  # type: ignore
IPython.get_ipython().run_line_magic("autoreload", "2")  # type: ignore

# %%

from docent import Docent
from docent_core._env_util import ENV

DOCENT_API_KEY = ENV.get("DOCENT_API_KEY")
DOCENT_DOMAIN = "docent-bridgewater.transluce.org"
if not DOCENT_DOMAIN or not DOCENT_API_KEY:
    raise ValueError("DOCENT_API_KEY and DOCENT_DOMAIN must be set")
dc = Docent(api_key=DOCENT_API_KEY, domain=DOCENT_DOMAIN)

# %%

import pandas as pd
from tqdm.auto import tqdm

pd.set_option("display.float_format", "{:.3f}".format)

cid = "..."  # Fill in your collection ID here
df = dc.dql_result_to_df_experimental(
    dc.execute_dql(
        cid,
        """
SELECT
    a.id AS agent_run_id,
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
    a.metadata_json ->> 'base_llm_name' != 'sonnet_4_5_thinking' AND
    a.metadata_json ->> 'llm_verbosity' != 'high'
GROUP BY
    a.id,
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
