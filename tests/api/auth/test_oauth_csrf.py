from unittest.mock import patch, AsyncMock
from urllib.parse import urlparse, parse_qs

import pytest
from fastapi.testclient import TestClient

from src.db.database import get_db
from src.main import app


@pytest.fixture
def oauth_client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    env = {
        "GOOGLE_CLIENT_ID": "test-client-id",
        "GOOGLE_CLIENT_SECRET": "test-client-secret",
        "GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/oauth/google/callback",
        "FRONTEND_URL": "http://localhost:3000",
    }

    with patch.dict("os.environ", env):
        with TestClient(app) as client:
            yield client

    app.dependency_overrides.clear()


def test_google_login_redirect_includes_state_param(oauth_client):
    response = oauth_client.get("/auth/oauth/google", follow_redirects=False)
    assert response.status_code in (302, 307)
    location = response.headers["location"]
    qs = parse_qs(urlparse(location).query)
    assert "state" in qs
    assert len(qs["state"][0]) > 8


def test_google_callback_missing_state_returns_400(oauth_client):
    response = oauth_client.get(
        "/auth/oauth/google/callback?code=testcode",
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "state" in response.json()["detail"].lower()


def test_google_callback_wrong_state_returns_400(oauth_client):
    oauth_client.get("/auth/oauth/google", follow_redirects=False)
    response = oauth_client.get(
        "/auth/oauth/google/callback?code=testcode&state=tampered_value",
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "state" in response.json()["detail"].lower()


def test_google_callback_valid_state_proceeds_past_csrf_check(oauth_client):
    login_resp = oauth_client.get("/auth/oauth/google", follow_redirects=False)
    location = login_resp.headers["location"]
    state = parse_qs(urlparse(location).query)["state"][0]

    mock_token_resp = AsyncMock()
    mock_token_resp.status_code = 400

    with patch("httpx.AsyncClient") as mock_cls:
        instance = mock_cls.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=mock_token_resp)
        response = oauth_client.get(
            f"/auth/oauth/google/callback?code=testcode&state={state}",
            follow_redirects=False,
        )

    assert response.status_code != 400 or "state" not in response.json().get("detail", "").lower()
