#%%
# IPython autoreload setup
try:
    from IPython import get_ipython

    ipython = get_ipython()
    if ipython is not None:
        ipython.run_line_magic("load_ext", "autoreload")
        ipython.run_line_magic("autoreload", "2")
except Exception:
    pass  # Not in IPython environment

#%%
from pathlib import Path

from docent.data_models.agent_run import AgentRun
from docent.sdk.client import Docent

COLLECTION_ID = "1094e0bf-5e7a-4448-9e35-55f60a8d7243"
OUTPUT_PATH = Path("collection_agent_runs_gitignore.json")

#%%
client = Docent(server_url="http://localhost:8901")
agent_run_ids = client.list_agent_run_ids(COLLECTION_ID)
print(f"Found {len(agent_run_ids)} agent runs in collection {COLLECTION_ID}")

#%%
agent_runs: list[AgentRun] = []

for i, agent_run_id in enumerate(agent_run_ids, start=1):
    sq_agent_run = client.get_agent_run(COLLECTION_ID, agent_run_id)
    if sq_agent_run is None:
        print(f"[{i}/{len(agent_run_ids)}] missing run: {agent_run_id}")
        continue

    # Re-validate explicitly so the output list is guaranteed pydantic-validatable.
    agent_runs.append(AgentRun.model_validate(sq_agent_run.model_dump(mode="json")))

    if i % 50 == 0:
        print(f"Downloaded {i}/{len(agent_run_ids)} runs")

print(f"Collected {len(agent_runs)} valid AgentRun models")

#%%
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
payload = [agent_run.model_dump(mode="json") for agent_run in agent_runs]
OUTPUT_PATH.write_text(__import__("json").dumps(payload, indent=2), encoding="utf-8")
print(f"Wrote {len(payload)} runs to {OUTPUT_PATH}")

# %%
