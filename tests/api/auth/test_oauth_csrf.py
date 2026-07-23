from unittest.mock import patch, AsyncMock
from urllib.parse import urlparse, parse_qs

import pytest
from fastapi.testclient import TestClient

from src.db.database import get_db
from src.db.tables import User
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


def test_google_callback_duplicate_email_returns_400(oauth_client, db):
    existing = User(
        email="dupe@example.com",
        username="dupeuser",
        firstname="Dupe",
        lastname="User",
        hashed_password="hashed",
    )
    db.add(existing)
    db.commit()

    login_resp = oauth_client.get("/auth/oauth/google", follow_redirects=False)
    location = login_resp.headers["location"]
    state = parse_qs(urlparse(location).query)["state"][0]

    mock_token_resp = AsyncMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json = lambda: {"access_token": "fake-google-access-token"}

    mock_userinfo_resp = AsyncMock()
    mock_userinfo_resp.json = lambda: {
        "email": "dupe@example.com",
        "email_verified": True,
        "sub": "google-sub-99999",
        "given_name": "Dupe",
        "family_name": "User",
        "picture": None,
    }

    with patch("httpx.AsyncClient") as mock_cls:
        instance = mock_cls.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=mock_token_resp)
        instance.get = AsyncMock(return_value=mock_userinfo_resp)
        response = oauth_client.get(
            f"/auth/oauth/google/callback?code=testcode&state={state}",
            follow_redirects=False,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Email already linked to another account"


def test_google_callback_new_user_avatar_url_is_none(oauth_client, db):
    login_resp = oauth_client.get("/auth/oauth/google", follow_redirects=False)
    location = login_resp.headers["location"]
    state = parse_qs(urlparse(location).query)["state"][0]

    mock_token_resp = AsyncMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json = lambda: {"access_token": "fake-google-access-token"}

    mock_userinfo_resp = AsyncMock()
    mock_userinfo_resp.json = lambda: {
        "email": "freshuser@example.com",
        "email_verified": True,
        "sub": "google-sub-fresh-1",
        "given_name": "Fresh",
        "family_name": "User",
        "picture": "https://example.com/photo.jpg",
    }

    with patch("httpx.AsyncClient") as mock_cls:
        instance = mock_cls.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=mock_token_resp)
        instance.get = AsyncMock(return_value=mock_userinfo_resp)
        response = oauth_client.get(
            f"/auth/oauth/google/callback?code=testcode&state={state}",
            follow_redirects=False,
        )

    assert response.status_code in (302, 307)
    user = db.query(User).filter(User.oauth_id == "google-sub-fresh-1").first()
    assert user is not None
    assert user.avatar_url is None
