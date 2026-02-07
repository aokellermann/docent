from unittest.mock import MagicMock, patch

import pytest

from docent.sdk.client import Docent


@pytest.mark.unit
def test_list_agent_run_ids_returns_plain_list() -> None:
    with patch.object(Docent, "_login"):
        client = Docent(api_key="test-key", domain="example.com")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = ["run-1", "run-2"]

    client._session.get = MagicMock(return_value=mock_response)  # type: ignore[method-assign, reportPrivateUsage]

    agent_run_ids = client.list_agent_run_ids("collection-123")

    client._session.get.assert_called_once_with(  # type: ignore[reportPrivateUsage]
        "https://api.example.com/rest/collection-123/agent_run_ids"
    )
    assert agent_run_ids == ["run-1", "run-2"]
