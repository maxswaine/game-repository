import os
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi.testclient import TestClient

from src.db.database import get_db
from src.db.tables import User
from src.main import app

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
FAKE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"

VALID_TOKENINFO = {
    "iss": "accounts.google.com",
    "aud": FAKE_CLIENT_ID,
    "sub": "google-sub-12345",
    "email": "testuser@gmail.com",
    "email_verified": "true",
    "given_name": "Test",
    "family_name": "User",
    "picture": "https://example.com/photo.jpg",
}


def _make_tokeninfo_mock(data: dict, status_code: int = 200):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = data
    return mock_resp


def _async_client_mock(data: dict, status_code: int = 200):
    mock_resp = _make_tokeninfo_mock(data, status_code)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=mock_client)


def _client(db):
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


# ---------------------------------------------------------------------------
# Success — new user
# ---------------------------------------------------------------------------

def test_google_token_new_user_returns_200(db):
    client = _client(db)
    try:
        with patch("src.api.auth.httpx.AsyncClient", _async_client_mock(VALID_TOKENINFO)), \
             patch.dict(os.environ, {"GOOGLE_CLIENT_ID": FAKE_CLIENT_ID}):
            response = client.post("/auth/oauth/google/token", json={"id_token": "fake-id-token"})
        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_google_token_new_user_returns_access_token(db):
    client = _client(db)
    try:
        with patch("src.api.auth.httpx.AsyncClient", _async_client_mock(VALID_TOKENINFO)), \
             patch.dict(os.environ, {"GOOGLE_CLIENT_ID": FAKE_CLIENT_ID}):
            response = client.post("/auth/oauth/google/token", json={"id_token": "fake-id-token"})
        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
    finally:
        app.dependency_overrides.clear()


def test_google_token_new_user_returns_is_new_user_true(db):
    client = _client(db)
    try:
        with patch("src.api.auth.httpx.AsyncClient", _async_client_mock(VALID_TOKENINFO)), \
             patch.dict(os.environ, {"GOOGLE_CLIENT_ID": FAKE_CLIENT_ID}):
            response = client.post("/auth/oauth/google/token", json={"id_token": "fake-id-token"})
        assert response.json()["is_new_user"] is True
    finally:
        app.dependency_overrides.clear()


def test_google_token_new_user_created_in_db(db):
    client = _client(db)
    try:
        with patch("src.api.auth.httpx.AsyncClient", _async_client_mock(VALID_TOKENINFO)), \
             patch.dict(os.environ, {"GOOGLE_CLIENT_ID": FAKE_CLIENT_ID}):
            client.post("/auth/oauth/google/token", json={"id_token": "fake-id-token"})
        user = db.query(User).filter(User.oauth_id == "google-sub-12345").first()
        assert user is not None
        assert user.email == "testuser@gmail.com"
        assert user.oauth_provider == "google"
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Success — returning user
# ---------------------------------------------------------------------------

def test_google_token_existing_user_returns_is_new_user_false(db):
    existing = User(
        email="testuser@gmail.com",
        username="testuser",
        firstname="Test",
        lastname="User",
        oauth_provider="google",
        oauth_id="google-sub-12345",
    )
    db.add(existing)
    db.commit()

    client = _client(db)
    try:
        with patch("src.api.auth.httpx.AsyncClient", _async_client_mock(VALID_TOKENINFO)), \
             patch.dict(os.environ, {"GOOGLE_CLIENT_ID": FAKE_CLIENT_ID}):
            response = client.post("/auth/oauth/google/token", json={"id_token": "fake-id-token"})
        assert response.json()["is_new_user"] is False
    finally:
        app.dependency_overrides.clear()


def test_google_token_existing_user_not_duplicated_in_db(db):
    existing = User(
        email="testuser@gmail.com",
        username="testuser",
        firstname="Test",
        lastname="User",
        oauth_provider="google",
        oauth_id="google-sub-12345",
    )
    db.add(existing)
    db.commit()

    client = _client(db)
    try:
        with patch("src.api.auth.httpx.AsyncClient", _async_client_mock(VALID_TOKENINFO)), \
             patch.dict(os.environ, {"GOOGLE_CLIENT_ID": FAKE_CLIENT_ID}):
            client.post("/auth/oauth/google/token", json={"id_token": "fake-id-token"})
        count = db.query(User).filter(User.oauth_id == "google-sub-12345").count()
        assert count == 1
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Duplicate email
# ---------------------------------------------------------------------------

def test_google_token_duplicate_email_returns_400(db):
    existing = User(
        email="testuser@gmail.com",
        username="testuser",
        firstname="Test",
        lastname="User",
        hashed_password="hashed",
    )
    db.add(existing)
    db.commit()

    client = _client(db)
    try:
        with patch("src.api.auth.httpx.AsyncClient", _async_client_mock(VALID_TOKENINFO)), \
             patch.dict(os.environ, {"GOOGLE_CLIENT_ID": FAKE_CLIENT_ID}):
            response = client.post("/auth/oauth/google/token", json={"id_token": "fake-id-token"})
        assert response.status_code == 400
        assert response.json()["detail"] == "Email already linked to another account"
    finally:
        app.dependency_overrides.clear()


def test_google_token_duplicate_email_does_not_create_user(db):
    existing = User(
        email="testuser@gmail.com",
        username="testuser",
        firstname="Test",
        lastname="User",
        hashed_password="hashed",
    )
    db.add(existing)
    db.commit()

    client = _client(db)
    try:
        with patch("src.api.auth.httpx.AsyncClient", _async_client_mock(VALID_TOKENINFO)), \
             patch.dict(os.environ, {"GOOGLE_CLIENT_ID": FAKE_CLIENT_ID}):
            client.post("/auth/oauth/google/token", json={"id_token": "fake-id-token"})
        count = db.query(User).filter(User.email == "testuser@gmail.com").count()
        assert count == 1
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Validation failures
# ---------------------------------------------------------------------------

def test_google_token_missing_body_returns_422(db):
    client = _client(db)
    try:
        response = client.post("/auth/oauth/google/token", json={})
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_google_token_invalid_id_token_returns_400(db):
    client = _client(db)
    try:
        with patch("src.api.auth.httpx.AsyncClient", _async_client_mock({"error": "invalid_token"}, status_code=400)), \
             patch.dict(os.environ, {"GOOGLE_CLIENT_ID": FAKE_CLIENT_ID}):
            response = client.post("/auth/oauth/google/token", json={"id_token": "bad-token"})
        assert response.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_google_token_unverified_email_returns_400(db):
    unverified = {**VALID_TOKENINFO, "email_verified": "false"}
    client = _client(db)
    try:
        with patch("src.api.auth.httpx.AsyncClient", _async_client_mock(unverified)), \
             patch.dict(os.environ, {"GOOGLE_CLIENT_ID": FAKE_CLIENT_ID}):
            response = client.post("/auth/oauth/google/token", json={"id_token": "fake-id-token"})
        assert response.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_google_token_wrong_audience_returns_400(db):
    wrong_aud = {**VALID_TOKENINFO, "aud": "some-other-app.apps.googleusercontent.com"}
    client = _client(db)
    try:
        with patch("src.api.auth.httpx.AsyncClient", _async_client_mock(wrong_aud)), \
             patch.dict(os.environ, {"GOOGLE_CLIENT_ID": FAKE_CLIENT_ID}):
            response = client.post("/auth/oauth/google/token", json={"id_token": "fake-id-token"})
        assert response.status_code == 400
    finally:
        app.dependency_overrides.clear()
