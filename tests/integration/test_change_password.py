"""Integration tests for the password change endpoint."""

import httpx
import pytest

from docent_core.docent.db.schemas.auth_models import User

NEW_PASSWORD = "new_password_456"
WRONG_PASSWORD = "totally_wrong_password"
OLD_PASSWORD = "test_password_123"


@pytest.mark.integration
async def test_change_password_success(
    authed_client: httpx.AsyncClient,
    unauthorized_client: httpx.AsyncClient,
    test_user: User,
) -> None:
    response = await authed_client.post(
        "/rest/change_password",
        json={"old_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Password updated successfully"}

    # Old password should stop working
    old_login = await unauthorized_client.post(
        "/rest/login",
        json={"email": test_user.email, "password": OLD_PASSWORD},
    )
    assert old_login.status_code == 401

    # New password should authenticate
    new_login = await unauthorized_client.post(
        "/rest/login",
        json={"email": test_user.email, "password": NEW_PASSWORD},
    )
    assert new_login.status_code == 200
    body = new_login.json()
    assert body["user"]["email"] == test_user.email
    assert "session_id" in body

    # Ensure the new session cookie works for authenticated routes
    me_response = await unauthorized_client.get("/rest/me")
    assert me_response.status_code == 200


@pytest.mark.integration
async def test_change_password_rejects_incorrect_current_password(
    authed_client: httpx.AsyncClient,
    unauthorized_client: httpx.AsyncClient,
    test_user: User,
) -> None:
    response = await authed_client.post(
        "/rest/change_password",
        json={"old_password": WRONG_PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Current password is incorrect"

    # Original credentials remain valid
    original_login = await unauthorized_client.post(
        "/rest/login",
        json={"email": test_user.email, "password": OLD_PASSWORD},
    )
    assert original_login.status_code == 200

    # Rejected new password should fail to log in
    failed_new_login = await unauthorized_client.post(
        "/rest/login",
        json={"email": test_user.email, "password": NEW_PASSWORD},
    )
    assert failed_new_login.status_code == 401
