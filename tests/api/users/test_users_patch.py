from datetime import datetime, timezone, timedelta

import jwt
import pytest
from pydantic import ValidationError

from src.core.security import SECRET_KEY, ALGORITHM, TOKEN_EXPIRES_MINUTES
from src.models.user_models.user import UserUpdate, UserPasswordUpdate


def _make_token(username: str, ver: int = 0) -> str:
    payload = {
        "sub": username,
        "ver": ver,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRES_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def test_avatar_url_rejects_javascript_protocol():
    with pytest.raises(ValidationError):
        UserUpdate(avatar_url="javascript:alert(1)")


def test_avatar_url_rejects_http_protocol():
    with pytest.raises(ValidationError):
        UserUpdate(avatar_url="http://example.com/avatar.jpg")


def test_avatar_url_accepts_https():
    model = UserUpdate(avatar_url="https://example.com/avatar.jpg")
    assert model.avatar_url == "https://example.com/avatar.jpg"


def test_avatar_url_accepts_none():
    model = UserUpdate(avatar_url=None)
    assert model.avatar_url is None


def test_username_rejects_too_short():
    with pytest.raises(ValidationError):
        UserUpdate(username="ab")


def test_username_rejects_too_long():
    with pytest.raises(ValidationError):
        UserUpdate(username="a" * 31)


def test_username_rejects_invalid_characters():
    with pytest.raises(ValidationError):
        UserUpdate(username="bad name!")


def test_username_rejects_profanity():
    with pytest.raises(ValidationError):
        UserUpdate(username="fuckface")


def test_username_accepts_valid_value():
    model = UserUpdate(username="cool_user_42")
    assert model.username == "cool_user_42"


def test_username_accepts_none():
    model = UserUpdate(username=None)
    assert model.username is None


def test_new_password_rejects_too_short():
    with pytest.raises(ValidationError):
        UserPasswordUpdate(current_password="whatever", new_password="short1")


def test_new_password_rejects_too_long():
    with pytest.raises(ValidationError):
        UserPasswordUpdate(current_password="whatever", new_password="a" * 129)


def test_new_password_accepts_valid_length():
    model = UserPasswordUpdate(current_password="whatever", new_password="a" * 128)
    assert model.new_password == "a" * 128


def test_change_username_success(client_with_auth, test_user, db):
    response = client_with_auth.patch("/users/me", json={"username": "brand_new_name"})

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "brand_new_name"
    assert data["access_token"] is not None
    assert "access_token" in response.cookies

    db.refresh(test_user)
    assert test_user.username == "brand_new_name"


def test_change_username_duplicate_case_insensitive_rejected(client_with_auth, second_user):
    response = client_with_auth.patch("/users/me", json={"username": second_user.username.upper()})

    assert response.status_code == 400
    assert response.json()["detail"] == "Username taken"


def test_change_username_same_value_is_noop(client_with_auth, test_user):
    response = client_with_auth.patch("/users/me", json={"username": test_user.username})

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] is None
    assert "access_token" not in response.cookies


def test_patch_other_fields_does_not_reissue_token(client_with_auth):
    response = client_with_auth.patch("/users/me", json={"firstname": "Newname"})

    assert response.status_code == 200
    data = response.json()
    assert data["firstname"] == "Newname"
    assert data["access_token"] is None
    assert "access_token" not in response.cookies


def test_new_token_from_username_change_works(client_no_auth, test_user):
    old_token = _make_token(test_user.username, ver=test_user.token_version or 0)
    change_response = client_no_auth.patch(
        "/users/me",
        json={"username": "renamed_user"},
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
