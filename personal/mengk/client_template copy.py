# autoflake: skip_file
# pyright: ignore

# %%

import IPython

IPython.get_ipython().run_line_magic("load_ext", "autoreload")
IPython.get_ipython().run_line_magic("autoreload", "2")

# %%

from docent import Docent
from docent_core._env_util import ENV

DOCENT_API_KEY = ENV.get("DOCENT_API_KEY")
DOCENT_DOMAIN = ENV.get("DOCENT_DOMAIN")
if not DOCENT_DOMAIN or not DOCENT_API_KEY:
    raise ValueError("DOCENT_API_KEY and DOCENT_DOMAIN must be set")
client = Docent(api_key=DOCENT_API_KEY, server_url=f"http://{DOCENT_DOMAIN}")

# %%

from docent.data_models.formatted_objects import FormattedAgentRun, FormattedTranscript
from docent.sdk.llm_context import LLMContext

collection_id = "96fad7bd-eb81-4da6-95d9-d66e94ff1533"  # change as needed

# %%
# 1. chat about 2 specific agent runs
run_ids = [
    "c25827b1-333b-4555-87fb-e1450969f56b",
    "ecada666-ce38-4b16-b098-a22590df09b4",
]
context = LLMContext()
for run_id in run_ids:
    run = client.get_agent_run(collection_id, run_id)
    assert run is not None
    context.add(run)

client.start_chat(context, model_string="openai/gpt-5-mini", reasoning_effort="low")

# %%
# 2. chat about individual transcripts (LLM won't see other transcripts in the run)
run_ids = ["da62ab48-ca38-4f29-8a47-fee15fb0ac4c", "8ed11e3b-1c67-4dcd-8078-96c9e0a994b6"]
context = LLMContext()
for run_id in run_ids:
    run = client.get_agent_run(collection_id, run_id)
    assert run is not None
    for transcript in run.transcripts:
        # suppose we only want to analyze the "verification" step and transcripts are named accordingly
        if transcript.name is not None and "verification" in transcript.name.lower():
            context.add(transcript)

client.start_chat(context, model_string="openai/gpt-5-mini", reasoning_effort="low")

# 3. select parts of a transcript to show/hide from the LLM
run_ids = ["da62ab48-ca38-4f29-8a47-fee15fb0ac4c", "8ed11e3b-1c67-4dcd-8078-96c9e0a994b6"]
context = LLMContext()
for run_id in run_ids:
    run = client.get_agent_run(collection_id, run_id)
    assert run is not None
    # FormattedAgentRun/FormattedTranscript let us control how we present runs/transcripts to the LLM
    run = FormattedAgentRun.from_agent_run(run)
    for i, transcript in enumerate(run.transcripts):
        formatted_transcript = FormattedTranscript.from_transcript(transcript)
        # hide the first message of each transcript from the LLM
        # note: the UI will still show the original transcript
        formatted_transcript.messages = formatted_transcript.messages[1:]
        run.transcripts[i] = formatted_transcript
    context.add(run)

client.start_chat(context, model_string="openai/gpt-5-mini", reasoning_effort="low")
