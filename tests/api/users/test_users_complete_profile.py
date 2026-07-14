from datetime import datetime, timezone, timedelta

import jwt
import pytest
from pydantic import ValidationError

from src.core.security import SECRET_KEY, ALGORITHM, TOKEN_EXPIRES_MINUTES
from src.models.user_models.user import UserCompleteProfile


def _make_token(username: str, ver: int = 0) -> str:
    payload = {
        "sub": username,
        "ver": ver,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRES_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def test_complete_profile_under_13_returns_422(client_with_auth):
    payload = {"date_of_birth": "2015-01-01", "country_of_origin": "US"}
    response = client_with_auth.post("/users/me/complete-profile", json=payload)

    assert response.status_code == 422
    assert "13" in response.text


def test_complete_profile_saves_dob_and_country(client_with_auth, test_user, db):
    payload = {"date_of_birth": "1990-06-15", "country_of_origin": "US"}
    response = client_with_auth.post("/users/me/complete-profile", json=payload)

    assert response.status_code == 200

    db.refresh(test_user)
    assert test_user.date_of_birth == "1990-06-15"
    assert test_user.country_of_origin == "US"


def test_complete_profile_response_reflects_updated_fields(client_with_auth, test_user, db):
    payload = {"date_of_birth": "1995-12-01", "country_of_origin": "DE"}
    response = client_with_auth.post("/users/me/complete-profile", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["country_of_origin"] == "DE"


def test_complete_profile_username_rejects_too_short():
    with pytest.raises(ValidationError):
        UserCompleteProfile(date_of_birth="1990-01-01", country_of_origin="US", username="ab")


def test_complete_profile_username_rejects_invalid_characters():
    with pytest.raises(ValidationError):
        UserCompleteProfile(date_of_birth="1990-01-01", country_of_origin="US", username="bad name!")


def test_complete_profile_username_rejects_profanity():
    with pytest.raises(ValidationError):
        UserCompleteProfile(date_of_birth="1990-01-01", country_of_origin="US", username="fuckface")


def test_complete_profile_username_accepts_valid_value():
    model = UserCompleteProfile(date_of_birth="1990-01-01", country_of_origin="US", username="cool_user_42")
    assert model.username == "cool_user_42"


def test_complete_profile_username_accepts_none():
    model = UserCompleteProfile(date_of_birth="1990-01-01", country_of_origin="US")
    assert model.username is None


def test_complete_profile_with_username_success(client_with_auth, test_user, db):
    payload = {"date_of_birth": "1990-06-15", "country_of_origin": "US", "username": "brand_new_name"}
    response = client_with_auth.post("/users/me/complete-profile", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "brand_new_name"
    assert data["access_token"] is not None
    assert "access_token" in response.cookies

    db.refresh(test_user)
    assert test_user.username == "brand_new_name"


def test_complete_profile_without_username_keeps_existing(client_with_auth, test_user, db):
    original_username = test_user.username
    payload = {"date_of_birth": "1990-06-15", "country_of_origin": "US"}
    response = client_with_auth.post("/users/me/complete-profile", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == original_username
    assert data["access_token"] is None
    assert "access_token" not in response.cookies


def test_complete_profile_username_duplicate_case_insensitive_rejected(client_with_auth, second_user):
    payload = {
        "date_of_birth": "1990-06-15",
        "country_of_origin": "US",
        "username": second_user.username.upper(),
    }
    response = client_with_auth.post("/users/me/complete-profile", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Username taken"


def test_complete_profile_username_same_value_is_noop(client_with_auth, test_user):
    payload = {
        "date_of_birth": "1990-06-15",
        "country_of_origin": "US",
        "username": test_user.username,
    }
    response = client_with_auth.post("/users/me/complete-profile", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] is None
    assert "access_token" not in response.cookies


def test_complete_profile_new_token_from_username_change_works(client_no_auth, test_user):
    old_token = _make_token(test_user.username, ver=test_user.token_version or 0)
    change_response = client_no_auth.post(
        "/users/me/complete-profile",
        json={"date_of_birth": "1990-06-15", "country_of_origin": "US", "username": "renamed_user"},
        headers={"Authorization": f"Bearer {old_token}"},
    )
    assert change_response.status_code == 200
    new_token = change_response.json()["access_token"]
    assert new_token is not None

    old_token_response = client_no_auth.get(
        "/users/me", headers={"Authorization": f"Bearer {old_token}"}
    )
    assert old_token_response.status_code == 404

    new_token_response = client_no_auth.get(
        "/users/me", headers={"Authorization": f"Bearer {new_token}"}
    )
    assert new_token_response.status_code == 200
    assert new_token_response.json()["username"] == "renamed_user"
