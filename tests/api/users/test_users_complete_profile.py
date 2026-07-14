import pytest
from pydantic import ValidationError

from src.models.user_models.user import UserCompleteProfile


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
