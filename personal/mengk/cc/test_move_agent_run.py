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
API_KEY = "dk_Tivd04d5dbcaWQKY_Nrl2OkL9KhBE8xhrUk7mwbsXye0IAiuhGNlXy72SljUXw4"  # TODO: fill in your API key

# Test data - fill these in
SOURCE_COLLECTION_ID = "2bd4b883-abba-46ad-bb8c-1f1448d51b8f"  # TODO: collection to move FROM
DESTINATION_COLLECTION_ID = "de8e8970-0678-4da4-b969-afe585f79257"  # TODO: collection to move TO
AGENT_RUN_ID = "eda21451-aed9-425d-81e6-82c2ec3ed375"  # TODO: agent run ID to move

#%%
# Helper to make authenticated requests
def get_headers():
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    return headers

#%%
# Test 1: Move agent run (happy path)
async def test_move_agent_run():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/rest/{SOURCE_COLLECTION_ID}/move_agent_run",
            json={
                "agent_run_id": AGENT_RUN_ID,
                "destination_collection_id": DESTINATION_COLLECTION_ID,
            },
            headers=get_headers(),
            timeout=30.0,
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        return response

response = await test_move_agent_run()

#%%
# Test 2: Move agent run back (reverse the move)
async def test_move_agent_run_back():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/rest/{DESTINATION_COLLECTION_ID}/move_agent_run",
            json={
                "agent_run_id": AGENT_RUN_ID,
                "destination_collection_id": SOURCE_COLLECTION_ID,
            },
            headers=get_headers(),
            timeout=30.0,
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        return response

# Uncomment to run:
# response = await test_move_agent_run_back()

#%%
# Test 3: Try to move non-existent agent run (should fail with 400)
async def test_move_nonexistent_agent_run():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/rest/{SOURCE_COLLECTION_ID}/move_agent_run",
            json={
                "agent_run_id": "nonexistent-agent-run-id",
                "destination_collection_id": DESTINATION_COLLECTION_ID,
            },
            headers=get_headers(),
            timeout=30.0,
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        return response

# Uncomment to run:
# response = await test_move_nonexistent_agent_run()

#%%
# Test 4: Try to move with missing agent_run_id (should fail with 422)
async def test_move_missing_agent_run_id():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/rest/{SOURCE_COLLECTION_ID}/move_agent_run",
            json={
                "agent_run_id": "missing-agent-run-id",
                "destination_collection_id": DESTINATION_COLLECTION_ID,
            },
            headers=get_headers(),
            timeout=30.0,
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        return response

# Uncomment to run:
response = await test_move_missing_agent_run_id()

#%%
# Test 5: Try to move to non-existent collection (should fail with 404)
async def test_move_to_nonexistent_collection():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/rest/{SOURCE_COLLECTION_ID}/move_agent_run",
            json={
                "agent_run_id": AGENT_RUN_ID,
                "destination_collection_id": "nonexistent-collection-id",
            },
            headers=get_headers(),
            timeout=30.0,
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        return response

# Uncomment to run:
response = await test_move_to_nonexistent_collection()

#%%
# Test 6: Verify agent run is in destination collection after move
async def verify_agent_run_location(collection_id: str, agent_run_id: str):
    """Check if an agent run exists in a specific collection."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/rest/{collection_id}/agent_run",
            params={"agent_run_id": agent_run_id},
            headers=get_headers(),
            timeout=30.0,
        )
        print(f"Checking agent run {agent_run_id} in collection {collection_id}")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Found: {data.get('id') if data else 'None'}")
        else:
            print(f"Response: {response.text}")
        return response

# Uncomment to run:
# await verify_agent_run_location(DESTINATION_COLLECTION_ID, AGENT_RUN_ID)

#%%
# Full integration test: move and verify
async def full_integration_test():
    print("=== Step 1: Verify agent run is in source collection ===")
    await verify_agent_run_location(SOURCE_COLLECTION_ID, AGENT_RUN_ID)

    print("\n=== Step 2: Move agent run to destination ===")
    move_response = await test_move_agent_run()

    if move_response.status_code == 200:
        print("\n=== Step 3: Verify agent run is now in destination collection ===")
        await verify_agent_run_location(DESTINATION_COLLECTION_ID, AGENT_RUN_ID)

        print("\n=== Step 4: Verify agent run is NOT in source collection ===")
        await verify_agent_run_location(SOURCE_COLLECTION_ID, AGENT_RUN_ID)
    else:
        print("\nMove failed, skipping verification steps")

# Uncomment to run full test:
# await full_integration_test()
