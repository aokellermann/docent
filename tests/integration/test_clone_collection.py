import httpx
import pytest

from docent.data_models import AgentRun, Transcript
from docent.data_models.chat import parse_chat_message
from docent_core.docent.db.contexts import ViewContext
from docent_core.docent.db.schemas.auth_models import User
from docent_core.docent.services.monoservice import MonoService

transcript_raw = [
    {"role": "user", "content": "Hello, how are you?"},
    {"role": "assistant", "content": "I'm doing well, thank you!"},
]


@pytest.mark.integration
async def test_clone_collection_via_api(
    authed_client: httpx.AsyncClient,
    test_collection_id: str,
    mono_service: MonoService,
    test_user: User,
):
    """Test cloning a collection via the REST API."""
    # Add some agent runs to the source collection
    agent_runs = [
        AgentRun(
            transcripts=[Transcript(messages=[parse_chat_message(msg) for msg in transcript_raw])],
            metadata={"test_key": "test_value_1"},
        ),
        AgentRun(
            transcripts=[Transcript(messages=[parse_chat_message(msg) for msg in transcript_raw])],
            metadata={"test_key": "test_value_2"},
        ),
    ]

    ctx = ViewContext(
        collection_id=test_collection_id,
        view_id="default",
        user=test_user,
        base_filter=None,
    )
    await mono_service.add_agent_runs(ctx, agent_runs)

    # Clone the collection via API
    response = await authed_client.post(
        f"/rest/{test_collection_id}/clone",
        json={
            "name": "Cloned Test Collection",
            "description": "This is a cloned collection",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "collection_id" in data
    assert data["status"] == "completed"
    assert data["agent_runs_cloned"] == 2

    cloned_collection_id = data["collection_id"]

    # Verify the cloned collection exists and has the right metadata
    response = await authed_client.get(f"/rest/{cloned_collection_id}/collection_details")
    assert response.status_code == 200
    collection_data = response.json()
    assert collection_data["name"] == "Cloned Test Collection"
    assert collection_data["description"] == "This is a cloned collection"
    assert collection_data["agent_run_count"] == 2

    # Verify agent runs were cloned
    cloned_ctx = ViewContext(
        collection_id=cloned_collection_id,
        view_id="default",
        user=test_user,
        base_filter=None,
    )
    cloned_agent_runs = await mono_service.get_agent_runs(cloned_ctx)
    assert len(cloned_agent_runs) == 2

    # Verify IDs are different (deep copy, not reference)
    original_agent_runs = await mono_service.get_agent_runs(ctx)
    original_ids = {ar.id for ar in original_agent_runs}
    cloned_ids = {ar.id for ar in cloned_agent_runs}
    assert original_ids.isdisjoint(cloned_ids)

    # Verify metadata is preserved
    cloned_metadata_values = {ar.metadata.get("test_key") for ar in cloned_agent_runs}
    assert cloned_metadata_values == {"test_value_1", "test_value_2"}


@pytest.mark.integration
async def test_clone_collection_direct_service(
    mono_service: MonoService,
    test_collection_id: str,
    test_user: User,
):
    """Test cloning a collection directly via the MonoService."""
    # Add agent runs to source collection
    agent_runs = [
        AgentRun(
            transcripts=[Transcript(messages=[parse_chat_message(msg) for msg in transcript_raw])],
            metadata={"index": i},
        )
        for i in range(3)
    ]

    ctx = ViewContext(
        collection_id=test_collection_id,
        view_id="default",
        user=test_user,
        base_filter=None,
    )
    await mono_service.add_agent_runs(ctx, agent_runs)

    # Clone the collection via service method
    new_collection_id, count = await mono_service.clone_collection(
        source_collection_id=test_collection_id,
        user=test_user,
        new_name="Service Cloned Collection",
        new_description="Cloned via service",
    )

    assert count == 3
    assert new_collection_id != test_collection_id

    # Verify agent runs were cloned
    cloned_ctx = ViewContext(
        collection_id=new_collection_id,
        view_id="default",
        user=test_user,
        base_filter=None,
    )
    cloned_agent_runs = await mono_service.get_agent_runs(cloned_ctx)
    assert len(cloned_agent_runs) == 3

    # Verify metadata is preserved
    cloned_indices = {ar.metadata.get("index") for ar in cloned_agent_runs}
    assert cloned_indices == {0, 1, 2}


@pytest.mark.integration
async def test_clone_empty_collection(
    authed_client: httpx.AsyncClient,
    test_collection_id: str,
):
    """Test cloning an empty collection."""
    # Clone without adding any agent runs
    response = await authed_client.post(
        f"/rest/{test_collection_id}/clone",
        json={},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["agent_runs_cloned"] == 0


@pytest.mark.integration
async def test_clone_nonexistent_collection(
    mono_service: MonoService,
    test_user: User,
):
    """Test that cloning a nonexistent collection raises an error."""
    with pytest.raises(ValueError, match="not found"):
        await mono_service.clone_collection(
            source_collection_id="nonexistent-collection-id",
            user=test_user,
        )
