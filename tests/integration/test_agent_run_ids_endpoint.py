import httpx
import pytest

from docent.data_models import AgentRun, Transcript
from docent.data_models.chat import parse_chat_message
from docent_core.docent.db.contexts import ViewContext
from docent_core.docent.db.schemas.auth_models import User
from docent_core.docent.services.monoservice import MonoService

TRANSCRIPT_RAW = [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi"},
]


async def _seed_agent_runs(
    mono_service: MonoService, test_collection_id: str, test_user: User, count: int
) -> None:
    agent_runs = [
        AgentRun(
            transcripts=[Transcript(messages=[parse_chat_message(msg) for msg in TRANSCRIPT_RAW])],
            metadata={"index": i},
        )
        for i in range(count)
    ]
    ctx = ViewContext(
        collection_id=test_collection_id,
        view_id="default",
        user=test_user,
        base_filter=None,
    )
    await mono_service.add_agent_runs(ctx, agent_runs)


@pytest.mark.integration
async def test_agent_run_ids_legacy_endpoint_returns_plain_list(
    authed_client: httpx.AsyncClient,
    test_collection_id: str,
    mono_service: MonoService,
    test_user: User,
) -> None:
    await _seed_agent_runs(mono_service, test_collection_id, test_user, count=3)

    response = await authed_client.get(
        f"/rest/{test_collection_id}/agent_run_ids",
        params={"sort_field": "agent_run_id", "sort_direction": "asc"},
    )
    assert response.status_code == 200

    payload: list[str] = response.json()
    assert isinstance(payload, list)
    assert len(payload) == 3
    assert all(isinstance(agent_run_id, str) for agent_run_id in payload)


@pytest.mark.integration
async def test_agent_run_ids_paginated_endpoint_returns_ids_and_has_more(
    authed_client: httpx.AsyncClient,
    test_collection_id: str,
    mono_service: MonoService,
    test_user: User,
) -> None:
    await _seed_agent_runs(mono_service, test_collection_id, test_user, count=3)

    first_page = await authed_client.get(
        f"/rest/{test_collection_id}/agent_run_ids_paginated",
        params={
            "sort_field": "agent_run_id",
            "sort_direction": "asc",
            "limit": 2,
            "offset": 0,
        },
    )
    assert first_page.status_code == 200

    first_payload = first_page.json()
    assert first_payload["has_more"] is True
    assert len(first_payload["ids"]) == 2

    second_page = await authed_client.get(
        f"/rest/{test_collection_id}/agent_run_ids_paginated",
        params={
            "sort_field": "agent_run_id",
            "sort_direction": "asc",
            "limit": 2,
            "offset": 2,
        },
    )
    assert second_page.status_code == 200

    second_payload = second_page.json()
    assert second_payload["has_more"] is False
    assert len(second_payload["ids"]) == 1
