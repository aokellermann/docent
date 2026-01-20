
#%%

import docent

client = docent.Docent()

collection_id = "ae533287-0fd1-4ede-860c-83c582c55c6d"
agent_run_id = "63e2da7d-15d1-4b70-8022-bfb05999a487"
result = client.get_agent_run(collection_id, agent_run_id)
print(f"Result: {result}")
# %%
