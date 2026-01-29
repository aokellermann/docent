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
# Imports
from docent.sdk.client import Docent
from docent.judges.types import Rubric
from docent.data_models.agent_run import AgentRun
from docent.data_models.transcript import Transcript
from docent.data_models.chat.message import UserMessage, AssistantMessage

#%%
# Initialize the client
# Make sure you have DOCENT_API_KEY set in environment or docent.env
client = Docent(server_url="http://localhost:8903")

# Use a test collection - replace with your collection ID
COLLECTION_ID = "13a40c7f-ed9b-4a2d-9659-3110534be5b6"  # TODO: Replace with actual collection ID

#%%
# Create some dummy AgentRuns for testing
def create_dummy_agent_run(task_description: str, agent_response: str, success: bool) -> AgentRun:
    """Create a simple dummy agent run with a single transcript."""
    transcript = Transcript(
        messages=[
            UserMessage(content=f"Task: {task_description}"),
            AssistantMessage(content=agent_response),
        ]
    )
    return AgentRun(
        name=f"Test run: {task_description[:30]}...",
        transcripts=[transcript],
        metadata={
            "task": task_description,
            "expected_success": success,
        },
    )


# Create a few test agent runs
dummy_runs = [
    create_dummy_agent_run(
        task_description="Calculate 2 + 2",
        agent_response="The answer is 4.",
        success=True,
    ),
    create_dummy_agent_run(
        task_description="Calculate 10 * 5",
        agent_response="The answer is 50.",
        success=True,
    ),
    create_dummy_agent_run(
        task_description="What is the capital of France?",
        agent_response="The capital of France is Berlin.",  # Wrong answer
        success=False,
    ),
]

print(f"Created {len(dummy_runs)} dummy agent runs")
for run in dummy_runs:
    print(f"  - {run.name} (id={run.id})")

#%%
# Step 1: Create a Rubric and upload it
rubric = Rubric(
    rubric_text="""
Evaluate whether the agent correctly answered the user's question.

Decision procedure:
1. Read the user's question carefully
2. Read the agent's response
3. Determine if the response is factually correct and answers the question

Output "pass" if the agent answered correctly, "fail" otherwise.
""".strip(),
    output_schema={
        "type": "object",
        "properties": {
            "label": {"type": "string", "enum": ["pass", "fail"]},
            "explanation": {"type": "string", "citations": True},
        },
        "required": ["label", "explanation"],
    },
)

print("Created rubric locally:")
print(f"  ID: {rubric.id}")
print(f"  Version: {rubric.version}")
print(f"  Rubric text preview: {rubric.rubric_text[:100]}...")

#%%
# Step 2: Upload the rubric to the server
rubric_id = client.create_rubric(COLLECTION_ID, rubric)
print(f"Uploaded rubric to server, got ID: {rubric_id}")

#%%
# Step 3: Download the rubric back from the server
downloaded_rubric = client.get_rubric(COLLECTION_ID, rubric_id)
print("Downloaded rubric from server:")
print(f"  ID: {downloaded_rubric.id}")
print(f"  Version: {downloaded_rubric.version}")
print(f"  Rubric text matches: {downloaded_rubric.rubric_text == rubric.rubric_text}")
print(f"\n  Full rubric details:")
print(f"    rubric_text:\n{downloaded_rubric.rubric_text}")
print(f"\n    output_schema: {downloaded_rubric.output_schema}")
print(f"    model_dump(): {downloaded_rubric.model_dump()}")

print(downloaded_rubric.model_dump_json(indent=2))


#%%
# Step 4: Get a judge from the rubric and run it on dummy agent runs
# Note: This requires LLM API keys (ANTHROPIC_API_KEY or OPENAI_API_KEY) to be set
judge = client.get_judge(COLLECTION_ID, rubric_id)
print(f"Got judge from rubric")
print(f"  Model: {judge.cfg.judge_model}")

#%%
# Step 5: Run the judge on each dummy agent run
# This is async, so we use await directly in interactive mode

results = []
for run in dummy_runs:
    print(f"\nJudging run: {run.name}")
    result = await judge(run)
    results.append(result)
    print(f"  Result type: {result.result_type}")
    print(f"  Output: {result.output}")

#%%
# Summary of results
print("\n" + "=" * 50)
print("SUMMARY")
print("=" * 50)
for run, result in zip(dummy_runs, results):
    expected = "pass" if run.metadata.get("expected_success") else "fail"
    actual = result.output.get("label", "unknown")
    match = "✓" if expected == actual else "✗"
    print(f"{match} {run.name}")
    print(f"    Expected: {expected}, Got: {actual}")
    print(f"    Explanation: {result.output.get('explanation', 'N/A')[:100]}...")

# %%
