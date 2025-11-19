# autoflake: skip_file
# pyright: ignore

# %%

import IPython

IPython.get_ipython().run_line_magic("load_ext", "autoreload")  # type: ignore
IPython.get_ipython().run_line_magic("autoreload", "2")  # type: ignore

# %%

from docent import Docent
from docent_core._env_util import ENV

# DOCENT_API_KEY = ENV.get("DOCENT_API_KEY")
# DOCENT_SERVER_URL = ENV.get("NEXT_PUBLIC_API_HOST")
# if not DOCENT_SERVER_URL or not DOCENT_API_KEY:
#     raise ValueError("DOCENT_API_KEY and DOCENT_SERVER_URL must be set")

DOCENT_API_KEY = ENV.get("DOCENT_API_KEY")
DOCENT_DOMAIN = ENV.get("DOCENT_DOMAIN")
if not DOCENT_DOMAIN or not DOCENT_API_KEY:
    raise ValueError("DOCENT_API_KEY and DOCENT_DOMAIN must be set")
dc = Docent(api_key=DOCENT_API_KEY, domain=DOCENT_DOMAIN)

# %%

import pandas as pd

pd.set_option("display.float_format", "{:.3f}".format)

cid = "8f334528-8bd6-41fe-8f61-35a5e25ea71b"
df = dc.dql_result_to_df_experimental(
    dc.execute_dql(
        cid,
        """
SELECT
    a.metadata_json ->> 'base_llm_name' AS base_llm_name,
    a.metadata_json ->> 'post_platt_scaling_probability' AS post_platt_scaling_probability,
    a.metadata_json ->> 'resolved_to' AS resolved_to,
    a.metadata_json ->> 'question' AS question,
FROM agent_runs a
""",
    )
)
rows_before = len(df)
df = df.dropna(subset=["base_llm_name", "post_platt_scaling_probability", "resolved_to"])
rows_after = len(df)
print(f"Dropped {rows_before - rows_after} rows (from {rows_before} to {rows_after})")

df["brier_score"] = (df["post_platt_scaling_probability"] - df["resolved_to"]) ** 2
df = df.sort_values(by="brier_score", ascending=False)
df

# %%

df_grouped = df[df["base_llm_name"].isin(["gpt-5", "o3"])].copy()
df_pivot = df_grouped.pivot_table(
    index="question", columns="base_llm_name", values="brier_score", aggfunc="first"
)
df_pivot = df_pivot.rename(columns={"gpt-5": "gpt5_brier_score", "o3": "o3_brier_score"})
rows_before_pivot = len(df_pivot)
df_pivot = df_pivot.dropna(subset=["gpt5_brier_score", "o3_brier_score"])
rows_after_pivot = len(df_pivot)
print(
    f"Dropped {rows_before_pivot - rows_after_pivot} rows (from {rows_before_pivot} to {rows_after_pivot})"
)
df_pivot["difference"] = df_pivot["gpt5_brier_score"] - df_pivot["o3_brier_score"]
df_pivot = df_pivot.sort_values(by="difference", ascending=False)

print(df_pivot["gpt5_brier_score"].mean())
print(df_pivot["o3_brier_score"].mean())

df_pivot

# %%
