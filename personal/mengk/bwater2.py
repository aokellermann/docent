# autoflake: skip_file
# pyright: ignore

# %%

import IPython

IPython.get_ipython().run_line_magic("load_ext", "autoreload")
IPython.get_ipython().run_line_magic("autoreload", "2")


# %%

from docent import Docent

d = Docent(
    api_key="dk_nfR2l2bQUmGfdcsv_pDlTVimPmKhA93BOfBeuyZFhkgDIx85926wfmuAeeB9Vjm",
    server_url="http://localhost:8890",
)
collection_id = "b0d737ce-a8d3-42fb-8570-aa53a6a60113"

# %%


ids = d.list_agent_run_ids(collection_id)
len(ids)


# %%


cur_id = "0c5834c4-7692-4587-b757-93094c465ebd"
ar = d.get_agent_run(collection_id, cur_id)


# %%


s = ar.to_text_new(indent=2)
print(s)

# %%

cur_id


# %%

from tqdm import tqdm

out = {}

for id in tqdm(ids):
    ar = d.get_agent_run(collection_id, id)
    out[id] = ar


# %%

import json

out_prc = [json.loads(item.model_dump_json()) for item in out.values()]


with open("agent_runs_gitignore.json", "w") as f:
    json.dump(out_prc, f)

# %%
