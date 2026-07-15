import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.db.database import get_db
from src.db.tables import User
from src.main import app

FAKE_BUNDLE_ID = "com.test.whatsthatgame"

VALID_CLAIMS = {
    "iss": "https://appleid.apple.com",
    "aud": FAKE_BUNDLE_ID,
    "sub": "apple-sub-12345",
    "email": "appleuser@privaterelay.appleid.com",
    "exp": 9999999999,
}


@pytest.fixture(autouse=True)
def set_apple_bundle_id():
    with patch.dict(os.environ, {"APPLE_BUNDLE_ID": FAKE_BUNDLE_ID}):
        yield


def _mock_verify(claims: dict = None, raises: Exception = None):
    if raises:
        async def _raise(*a, **kw):
            raise raises
        return _raise
    async def _ok(*a, **kw):
        return claims or VALID_CLAIMS
    return _ok


def _client(db):
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_apple_token_new_user_returns_200(db):
    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify()):
            response = client.post("/auth/oauth/apple/token", json={
                "identity_token": "fake-token",
                "firstname": "Max",
                "lastname": "Swaine",
            })
        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()


# Task 3: Response shape and is_new_user

def test_apple_token_new_user_returns_access_token(db):
    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify()):
            response = client.post("/auth/oauth/apple/token", json={
                "identity_token": "fake-token",
                "firstname": "Max",
                "lastname": "Swaine",
            })
        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
    finally:
        app.dependency_overrides.clear()


def test_apple_token_new_user_returns_is_new_user_true(db):
    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify()):
            response = client.post("/auth/oauth/apple/token", json={
                "identity_token": "fake-token",
                "firstname": "Max",
                "lastname": "Swaine",
            })
        assert response.json()["is_new_user"] is True
    finally:
        app.dependency_overrides.clear()


# Task 4: DB fields and name fallback

def test_apple_token_new_user_created_in_db(db):
    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify()):
            client.post("/auth/oauth/apple/token", json={
                "identity_token": "fake-token",
                "firstname": "Max",
                "lastname": "Swaine",
            })
        user = db.query(User).filter(User.oauth_id == "apple-sub-12345").first()
        assert user is not None
        assert user.email == "appleuser@privaterelay.appleid.com"
        assert user.oauth_provider == "apple"
        assert user.firstname == "Max"
        assert user.lastname == "Swaine"
        assert user.hashed_password is None
        assert user.avatar_url is None
    finally:
        app.dependency_overrides.clear()


def test_apple_token_new_user_without_name_uses_empty_strings(db):
    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify()):
            client.post("/auth/oauth/apple/token", json={
                "identity_token": "fake-token",
            })
        user = db.query(User).filter(User.oauth_id == "apple-sub-12345").first()
        assert user.firstname == ""
        assert user.lastname == ""
    finally:
        app.dependency_overrides.clear()


# Task 5: Returning user

def test_apple_token_existing_user_returns_is_new_user_false(db):
    existing = User(
        email="appleuser@privaterelay.appleid.com",
        username="appleuser",
        firstname="Max",
        lastname="Swaine",
        oauth_provider="apple",
        oauth_id="apple-sub-12345",
    )
    db.add(existing)
    db.commit()

    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify()):
            response = client.post("/auth/oauth/apple/token", json={
                "identity_token": "fake-token",
            })
        assert response.json()["is_new_user"] is False
    finally:
        app.dependency_overrides.clear()


def test_apple_token_existing_user_not_duplicated_in_db(db):
    existing = User(
        email="appleuser@privaterelay.appleid.com",
        username="appleuser",
        firstname="Max",
        lastname="Swaine",
        oauth_provider="apple",
        oauth_id="apple-sub-12345",
    )
    db.add(existing)
    db.commit()

    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify()):
            client.post("/auth/oauth/apple/token", json={"identity_token": "fake-token"})
        count = db.query(User).filter(User.oauth_id == "apple-sub-12345").count()
        assert count == 1
    finally:
        app.dependency_overrides.clear()


# Task 6: Inactive user reactivation

def test_apple_token_inactive_user_within_30_days_is_reactivated(db):
    inactive = User(
        email="appleuser@privaterelay.appleid.com",
        username="appleuser",
        firstname="Max",
        lastname="Swaine",
        oauth_provider="apple",
        oauth_id="apple-sub-12345",
        is_active=False,
        deletion_requested_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    db.add(inactive)
    db.commit()

    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify()):
            response = client.post("/auth/oauth/apple/token", json={"identity_token": "fake-token"})
        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert body["is_new_user"] is False
        db.refresh(inactive)
        assert inactive.is_active is True
        assert inactive.deletion_requested_at is None
    finally:
        app.dependency_overrides.clear()


# Task 7: Email conflict → 400

def test_apple_token_email_conflict_with_google_user_returns_400(db):
    google_user = User(
        email="appleuser@privaterelay.appleid.com",
        username="appleuser",
        firstname="Max",
        lastname="Swaine",
        oauth_provider="google",
        oauth_id="google-sub-99999",
    )
    db.add(google_user)
    db.commit()

    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify()):
            response = client.post("/auth/oauth/apple/token", json={"identity_token": "fake-token"})
        assert response.status_code == 400
        assert response.json()["detail"] == "Email already linked to another account"
    finally:
        app.dependency_overrides.clear()


def test_apple_token_email_conflict_case_insensitive_returns_400(db):
    google_user = User(
        email="AppleUser@PrivateRelay.AppleID.com",
        username="appleuser2",
        firstname="Max",
        lastname="Swaine",
        oauth_provider="google",
        oauth_id="google-sub-88888",
    )
    db.add(google_user)
    db.commit()

    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify()):
            response = client.post("/auth/oauth/apple/token", json={"identity_token": "fake-token"})
        assert response.status_code == 400
        assert response.json()["detail"] == "Email already linked to another account"
    finally:
        app.dependency_overrides.clear()


# Task 8: Invalid token and missing claims → 400

def test_apple_token_invalid_token_returns_400(db):
    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify(raises=ValueError("bad token"))):
            response = client.post("/auth/oauth/apple/token", json={"identity_token": "bad-token"})
        assert response.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_apple_token_missing_sub_returns_400(db):
    claims_no_sub = {**VALID_CLAIMS, "sub": None}
    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify(claims=claims_no_sub)):
            response = client.post("/auth/oauth/apple/token", json={"identity_token": "fake-token"})
        assert response.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_apple_token_new_user_missing_email_returns_400(db):
    claims_no_email = {**VALID_CLAIMS, "email": None}
    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify(claims=claims_no_email)):
            response = client.post("/auth/oauth/apple/token", json={"identity_token": "fake-token"})
        assert response.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_apple_token_returning_user_without_email_in_claims_succeeds(db):
    existing = User(
        email="appleuser@privaterelay.appleid.com",
        username="appleuser",
        firstname="Max",
        lastname="Swaine",
        oauth_provider="apple",
        oauth_id="apple-sub-12345",
    )
    db.add(existing)
    db.commit()

    claims_no_email = {**VALID_CLAIMS, "email": None}
    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify(claims=claims_no_email)):
            response = client.post("/auth/oauth/apple/token", json={"identity_token": "fake-token"})
        assert response.status_code == 200
        assert response.json()["is_new_user"] is False
    finally:
        app.dependency_overrides.clear()


def test_apple_token_missing_body_returns_422(db):
    client = _client(db)
    try:
        response = client.post("/auth/oauth/apple/token", json={})
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
