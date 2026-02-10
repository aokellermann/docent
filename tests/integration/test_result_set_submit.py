from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from docent.data_models.agent_run import AgentRun
from docent.data_models.chat.message import AssistantMessage, UserMessage
from docent.data_models.transcript import Transcript
from docent.sdk.llm_context import AgentRunRef, Prompt
from docent.sdk.llm_request import ExternalAnalysisResult, LLMRequest
from docent_core.docent.db.schemas.auth_models import User
from docent_core.docent.services.monoservice import MonoService

if TYPE_CHECKING:
    import httpx


@pytest.mark.integration
async def test_submit_results_endpoint_new_result_set_direct_results(
    authed_client: "httpx.AsyncClient",
    mono_service: MonoService,
    test_collection_id: str,
    test_user: User,
) -> None:
    """POST /results/{collection_id}/submit/{name} succeeds for direct results on new set."""
    agent_run = AgentRun(
        transcripts=[
            Transcript(
                messages=[
                    UserMessage(content="Hello"),
                    AssistantMessage(content="Hi there"),
                ]
            )
        ]
    )
    ctx = await mono_service.get_default_view_ctx(test_collection_id, test_user)
    await mono_service.add_agent_runs(ctx=ctx, agent_runs=[agent_run])

    result_set_name = f"rest-direct-{uuid4()}"
    external_result = ExternalAnalysisResult(
        request=LLMRequest(
            prompt=Prompt([AgentRunRef(id=agent_run.id, collection_id=test_collection_id)])
        ),
        output={"output": "ok"},
    )
    submit_response = await authed_client.post(
        f"/rest/results/{test_collection_id}/submit/{result_set_name}",
        json={"results": [external_result.model_dump(mode="json")]},
    )
    assert submit_response.status_code == 200
    submit_data = submit_response.json()
    assert submit_data["result_set_id"]

    get_response = await authed_client.get(
        f"/rest/results/{test_collection_id}/results/{result_set_name}"
    )
    assert get_response.status_code == 200
    stored_results = get_response.json()
    assert len(stored_results) == 1
    assert stored_results[0]["output"] == {"output": "ok"}
