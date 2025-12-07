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

pd.set_option("display.float_format", "{:.3f}".format)

cid = "1f80cbbe-3b82-45db-9570-eb20346fe200"
df = dc.dql_result_to_df_experimental(
    dc.execute_dql(
        cid,
        """
SELECT
    jr_big.agent_run_id AS agent_run_id,
    jr_big.output ->> 'label' AS label_big,
    jr_small.output ->> 'label' AS label_small,
FROM judge_results jr_big
JOIN judge_results jr_small ON jr_big.agent_run_id = jr_small.agent_run_id
WHERE
    jr_big.rubric_id = '048d4801-9397-4a9b-9c8c-14b0368659f3' AND
    jr_big.rubric_version = 1 AND
    jr_small.rubric_version = 3
""",
    )
)
rows_before = len(df)
df = df.dropna()
rows_after = len(df)
print(f"Dropped {rows_before - rows_after} rows (from {rows_before} to {rows_after})")
df

# %%

# Measure agreement between label_big and label_small
df["agreement"] = df["label_big"] == df["label_small"]

# Calculate overall agreement rate
agreement_rate = df["agreement"].mean()
print(f"Agreement rate: {agreement_rate:.3f} ({df['agreement'].sum()}/{len(df)})")

df

# %%
