import httpx
import pytest


@pytest.mark.integration
async def test_upload_file(test_collection_id: str, authed_client: httpx.AsyncClient):
    with open("tests/integration/data/ctf.json", "rb") as f:
        file_content = f.read()
    response = await authed_client.post(
        f"/rest/{test_collection_id}/preview_import_runs_from_file",
        files={"file": ("abc.json", file_content, "application/json")},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["would_import"]["num_agent_runs"] == 2
    assert data["file_info"]["filename"] == "abc.json"

    # First run has a score of "C" for correct
    assert data["sample_preview"][0]["metadata"]["scores"]["includes"] == 1

    # Second run has a score of "I" for incorrect
    assert data["sample_preview"][1]["metadata"]["scores"]["includes"] == 0
