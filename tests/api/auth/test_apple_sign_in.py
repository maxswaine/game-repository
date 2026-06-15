import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

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
