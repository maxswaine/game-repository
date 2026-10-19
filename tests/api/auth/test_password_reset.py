import logging

import pytest
from pydantic import ValidationError

import src.api.auth
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


class TestForgotPasswordEmailFailure:
    """A failing reset email must stay invisible to the caller but visible in the logs.

    The response is deliberately identical whether or not the address is registered, so
    surfacing the error would leak account existence. That makes logging the only signal
    there is — without it a broken Resend key black-holes every reset silently.
    """

    def _break_email(self, monkeypatch):
        def raise_it(*args, **kwargs):
            raise RuntimeError("resend is down")

        monkeypatch.setattr(src.api.auth, "send_password_reset_email", raise_it)

    def test_still_returns_generic_success(self, client_no_auth, test_user, monkeypatch):
        self._break_email(monkeypatch)
        response = client_no_auth.post("/auth/forgot-password", json={"email": test_user.email})
        assert response.status_code == 200
        assert "a reset link has been sent" in response.json()["message"]

    def test_logs_the_failure(self, client_no_auth, test_user, monkeypatch, caplog):
        self._break_email(monkeypatch)
        with caplog.at_level(logging.ERROR, logger="src.api.auth"):
            client_no_auth.post("/auth/forgot-password", json={"email": test_user.email})
        assert any("Password reset email failed" in r.message for r in caplog.records)
