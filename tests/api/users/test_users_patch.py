import pytest
from pydantic import ValidationError

from src.models.user_models.user import UserUpdate


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
