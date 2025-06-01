# autoflake: skip_file
# pyright: ignore

# %%

import IPython

IPython.get_ipython().run_line_magic("load_ext", "autoreload")
IPython.get_ipython().run_line_magic("autoreload", "2")

# %%

from docent._db_service.service import DBService

db_service = await DBService.init()


# %%

await db_service.get_fgs()


# %%

ctx = await db_service.get_default_view_ctx(fg_id)

# %%

ctx

# %%


fg_id = "677791bc-0891-4605-9cfa-150e6187543d"
run = await db_service.get_any_agent_run(ctx)
