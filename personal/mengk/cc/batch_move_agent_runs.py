# pyright: ignore
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
# Configuration - fill these in
import httpx

BASE_URL = "http://localhost:8901"  # TODO: fill in your base URL
API_KEY = "..."  # TODO: fill in your API key

# Collection IDs
SOURCE_COLLECTION_ID = "2bd4b883-abba-46ad-bb8c-1f1448d51b8f"  # TODO: collection to move FROM
DESTINATION_COLLECTION_ID = "de8e8970-0678-4da4-b969-afe585f79257"  # TODO: collection to move TO

# Batch size for pagination
BATCH_SIZE = 1000

# Dry run mode - set to False to actually perform moves
DRY_RUN = False

# DQL query to find agent runs to move (modify as needed)
# DQL_QUERY_TEMPLATE = """
# SELECT id, metadata_json ->> 'wandb_name'
# FROM agent_runs
# WHERE collection_id = '{source_collection_id}'
#   AND (metadata_json ->> 'wandb_name') NOT LIKE 'eps-simplified-8q%'
#   AND (metadata_json ->> 'wandb_name') NOT LIKE 'eps-simplified-4q%'
#   AND (metadata_json ->> 'wandb_name') NOT LIKE 'eps-simplified-focused%'
#   AND (metadata_json ->> 'wandb_name') NOT LIKE 'eps-simplified-maximal%'
# LIMIT {batch_size} OFFSET {{offset}}
# """

DQL_QUERY_TEMPLATE = """
SELECT id, metadata_json ->> 'wandb_name'
FROM agent_runs
WHERE collection_id = '{source_collection_id}'
  AND (metadata_json ->> 'extra_field_003') = 'false'
LIMIT {batch_size} OFFSET {{offset}}
"""


#%%
# Helper to make authenticated requests
def get_headers():
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    return headers


#%%
# Execute a single DQL query
async def execute_dql_query(query: str) -> dict:
    """Execute a DQL query and return the response."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/rest/dql/{SOURCE_COLLECTION_ID}/execute",
            json={"dql": query},
            headers=get_headers(),
            timeout=120.0,
        )
        if response.status_code != 200:
            print(f"DQL query failed: {response.status_code}")
            print(f"Response: {response.text}")
            response.raise_for_status()
        return response.json()


#%%
# Move a single agent run
async def move_agent_run(client: httpx.AsyncClient, agent_run_id: str) -> None:
    """Move a single agent run to the destination collection. Raises on failure."""
    response = await client.post(
        f"{BASE_URL}/rest/{SOURCE_COLLECTION_ID}/move_agent_run",
        json={
            "agent_run_id": agent_run_id,
            "destination_collection_id": DESTINATION_COLLECTION_ID,
        },
        headers=get_headers(),
        timeout=30.0,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to move {agent_run_id}: {response.status_code} - {response.text}"
        )


#%%
# Main batch move function
async def batch_move_agent_runs():
    """Orchestrate the batch move of agent runs using streaming fetch+move."""
    # Validate configuration
    if not API_KEY:
        print("ERROR: API_KEY is not set")
        return
    if not DESTINATION_COLLECTION_ID:
        print("ERROR: DESTINATION_COLLECTION_ID is not set")
        return

    print("=" * 60)
    print("Batch Move Agent Runs (Streaming)")
    print("=" * 60)
    print(f"Mode:                   {'DRY RUN' if DRY_RUN else 'LIVE'}")
    print(f"Source Collection:      {SOURCE_COLLECTION_ID}")
    print(f"Destination Collection: {DESTINATION_COLLECTION_ID}")
    print("=" * 60)
    if DRY_RUN:
        print("\n*** DRY RUN MODE - No moves will be performed ***")

    # Stream fetch + move in batches
    print("\nFetching and moving agent runs in batches...")
    total_count = 0
    offset = 0
    batch_num = 0

    async with httpx.AsyncClient() as client:
        while True:
            batch_num += 1
            query = DQL_QUERY_TEMPLATE.format(
                source_collection_id=SOURCE_COLLECTION_ID, batch_size=BATCH_SIZE
            ).format(offset=offset)

            print(f"\n[Batch {batch_num}] Fetching at offset {offset}...")
            result = await execute_dql_query(query)
            rows = result.get("rows", [])
            batch_count = len(rows)

            if batch_count == 0:
                print("  No more agent runs to move.")
                break

            # Extract agent run IDs (first column)
            batch_ids = [row[0] for row in rows]
            print(f"  Fetched {batch_count} agent runs, moving...")

            # Move this batch (or print IDs in dry run mode)
            for i, agent_run_id in enumerate(batch_ids):
                if (i + 1) % 100 == 0:
                    print(f"    Progress: {i + 1}/{batch_count}")

                if DRY_RUN:
                    print(f"    [DRY RUN] Would move: {agent_run_id}")
                else:
                    await move_agent_run(client, agent_run_id)

            total_count += batch_count
            print(f"  Batch complete: {batch_count} moved")

            # Check if we've processed all results
            if batch_count < BATCH_SIZE:
                print("  Last batch reached (fewer than BATCH_SIZE results)")
                break

            offset += BATCH_SIZE

    # Summary
    print("\n" + "=" * 60)
    print("Summary" + (" (DRY RUN)" if DRY_RUN else ""))
    print("=" * 60)
    print(f"Total:     {total_count}")
    if DRY_RUN:
        print(f"Would move: {total_count}")
    else:
        print(f"Moved:     {total_count}")
    print("=" * 60)


#%%
# Run the batch move (uncomment to execute)
await batch_move_agent_runs()

# %%
