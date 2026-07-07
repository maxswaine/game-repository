from datetime import datetime, timezone, timedelta

import jwt
import pytest

from src.core.security import SECRET_KEY, ALGORITHM, TOKEN_EXPIRES_MINUTES, create_access_token


def _make_token(username: str, ver: int = 0, exp_delta: timedelta = None) -> str:
    payload = {"sub": username, "ver": ver}
    if exp_delta is not None:
        payload["exp"] = datetime.now(timezone.utc) + exp_delta
    else:
        payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRES_MINUTES)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def test_refresh_valid_token(client_no_auth, test_user):
    token = _make_token(test_user.username, ver=test_user.token_version or 0)
    response = client_no_auth.post("/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_refresh_expired_token_succeeds(client_no_auth, test_user):
    """Expired token must still refresh — covers the app-backgrounding logout bug."""
    token = _make_token(test_user.username, ver=test_user.token_version or 0, exp_delta=timedelta(seconds=-1))
    response = client_no_auth.post("/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_refresh_revoked_token_rejected(client_no_auth, test_user):
    """Token with stale ver (e.g. after logout) must be rejected."""
    stale_ver = (test_user.token_version or 0) - 1
    token = _make_token(test_user.username, ver=stale_ver)
    response = client_no_auth.post("/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["detail"]["reason"] == "token_revoked"


def test_refresh_tampered_token_rejected(client_no_auth):
    response = client_no_auth.post("/auth/refresh", headers={"Authorization": "Bearer not.a.token"})
    assert response.status_code == 401
    assert response.json()["detail"]["reason"] == "invalid_token"


def test_refresh_no_token_rejected(client_no_auth):
    response = client_no_auth.post("/auth/refresh")
    assert response.status_code == 401
    assert response.json()["detail"]["reason"] == "no_token"


def test_refresh_very_old_expired_token_rejected(client_no_auth, test_user):
    """Token expired > 30 days ago must be rejected even with valid signature."""
    token = _make_token(test_user.username, ver=test_user.token_version or 0, exp_delta=timedelta(days=-31))
    response = client_no_auth.post("/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["detail"]["reason"] == "session_expired"


def test_refresh_sets_cookie(client_no_auth, test_user):
    token = _make_token(test_user.username, ver=test_user.token_version or 0)
    response = client_no_auth.post("/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert "access_token" in response.cookies
