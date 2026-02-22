# autoflake: skip_file
# pyright: ignore

"""
Script to ingest 20K agent runs with 100 shared metadata fields.
"""

# %%

try:
    import IPython

    if IPython.get_ipython() is not None:
        IPython.get_ipython().run_line_magic("load_ext", "autoreload")  # type: ignore
        IPython.get_ipython().run_line_magic("autoreload", "2")  # type: ignore
except Exception:
    pass

# %%

import random
import string
from uuid import uuid4

from docent import Docent
from docent.data_models.agent_run import AgentRun
from docent.data_models.chat import AssistantMessage, UserMessage
from docent.data_models.transcript import Transcript
from docent_core._env_util import ENV

# %%

# Initialize client
DOCENT_API_KEY = ENV.get("DOCENT_API_KEY")
DOCENT_DOMAIN = ENV.get("DOCENT_DOMAIN")
if not DOCENT_DOMAIN or not DOCENT_API_KEY:
    raise ValueError("DOCENT_API_KEY and DOCENT_DOMAIN must be set")

# Use HTTP for localhost, HTTPS otherwise
use_https = "localhost" not in DOCENT_DOMAIN
dc = Docent(api_key=DOCENT_API_KEY, domain=DOCENT_DOMAIN)

# %%

# Configuration
NUM_AGENT_RUNS = 20_000
NUM_METADATA_FIELDS = 100
NUM_EXTRA_FIELDS = 100

# Define the 100 metadata field names that will be shared across all runs
METADATA_FIELD_NAMES = [f"field_{i:03d}" for i in range(NUM_METADATA_FIELDS)]
# Define 100 additional metadata field names that will have random presence/absence
EXTRA_FIELD_NAMES = [f"extra_field_{i:03d}" for i in range(NUM_EXTRA_FIELDS)]


def generate_random_value(field_idx: int) -> str | int | float | bool:
    """Generate a random value for a metadata field based on its index."""
    field_type = field_idx % 4
    if field_type == 0:
        # String value
        return "".join(random.choices(string.ascii_lowercase, k=random.randint(5, 20)))
    elif field_type == 1:
        # Integer value
        return random.randint(0, 10000)
    elif field_type == 2:
        # Float value
        return round(random.uniform(0, 100), 4)
    else:
        # Boolean value
        return random.choice([True, False])


def generate_metadata() -> dict:
    """Generate metadata with all 100 fields populated with random values.

    Additionally includes 100 extra fields where each field is randomly either:
    - Omitted (not in the dict)
    - Explicitly set to None
    - Populated with a random value
    """
    metadata = {
        field_name: generate_random_value(i) for i, field_name in enumerate(METADATA_FIELD_NAMES)
    }

    # For the extra fields, randomly assign each to one of three groups
    # We'll use a simple random choice for each field
    for i, field_name in enumerate(EXTRA_FIELD_NAMES):
        choice = random.randint(0, 2)
        if choice == 0:
            # Omit this field entirely (don't add to dict)
            pass
        elif choice == 1:
            # Explicitly set to None
            metadata[field_name] = None
        else:
            # Populate with a random value
            metadata[field_name] = generate_random_value(i)

    return metadata


def generate_agent_run(run_idx: int) -> AgentRun:
    """Generate a single agent run with metadata and a simple transcript."""
    run_id = str(uuid4())

    # Create a simple transcript with a user message and assistant response
    transcript = Transcript(
        messages=[
            UserMessage(content=f"This is test run {run_idx}. What is {run_idx} + 1?"),
            AssistantMessage(content=f"The answer is {run_idx + 1}."),
        ],
        metadata={"transcript_index": run_idx},
    )

    return AgentRun(
        id=run_id,
        name=f"Test Run {run_idx}",
        description=f"Auto-generated test run #{run_idx}",
        transcripts=[transcript],
        metadata=generate_metadata(),
    )


# %%

# Create a new collection for this test
collection_id = dc.create_collection(
    name="20K Agent Runs Test",
    description="Collection with 20K agent runs, each having 100 metadata fields",
)
print(f"Created collection: {collection_id}")

# %%

# Generate all agent runs
print(f"Generating {NUM_AGENT_RUNS} agent runs...")
agent_runs = [generate_agent_run(i) for i in range(NUM_AGENT_RUNS)]
print(f"Generated {len(agent_runs)} agent runs")

# %%

# Upload agent runs to the collection
print(f"Uploading {len(agent_runs)} agent runs to collection {collection_id}...")
result = dc.add_agent_runs(collection_id, agent_runs)
print(f"Upload result: {result}")

# %%

# Verify the upload
print(f"\nCollection URL: https://{DOCENT_DOMAIN}/dashboard/{collection_id}")
