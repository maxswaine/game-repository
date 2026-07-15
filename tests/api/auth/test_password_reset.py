import pytest
from pydantic import ValidationError

from src.api.auth import ResetPasswordRequest


def test_new_password_rejects_too_short():
    with pytest.raises(ValidationError):
        ResetPasswordRequest(token="whatever", new_password="short1")


def test_new_password_rejects_too_long():
    with pytest.raises(ValidationError):
        ResetPasswordRequest(token="whatever", new_password="a" * 129)


def test_new_password_accepts_valid_length():
    model = ResetPasswordRequest(token="whatever", new_password="a" * 128)
    assert model.new_password == "a" * 128
