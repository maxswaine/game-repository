import re

from src.api.auth import generate_random_username
from src.core.security import create_password_reset_token

_RANDOM_USERNAME_RE = re.compile(r"^[A-Z][a-zA-Z]+\d{1,2}$")


def test_generate_random_username_matches_expected_format():
    username = generate_random_username()
    assert _RANDOM_USERNAME_RE.match(username), username


def test_generate_random_username_varies_across_calls():
    usernames = {generate_random_username() for _ in range(20)}
    assert len(usernames) > 1


def test_reset_password_double_submit_is_idempotent(client_no_auth, test_user):
    token = create_password_reset_token(test_user.email, test_user.token_version or 0)

    first = client_no_auth.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "NewPassword456"},
    )
    assert first.status_code == 200

    second = client_no_auth.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "NewPassword456"},
    )
    assert second.status_code == 200
    assert second.json() == {"message": "Password reset successfully"}

    login = client_no_auth.post(
        "/auth/token",
        data={"username": "testuser", "password": "NewPassword456"},
    )
    assert login.status_code == 200


def test_reset_password_clears_stale_session_cookie(client_no_auth, test_user):
    token = create_password_reset_token(test_user.email, test_user.token_version or 0)

    response = client_no_auth.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "NewPassword456"},
    )
    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "")
    assert "access_token=" in set_cookie
    assert "Max-Age=0" in set_cookie or "expires=Thu, 01 Jan 1970" in set_cookie


def test_reset_password_replay_with_different_password_rejected(client_no_auth, test_user):
    token = create_password_reset_token(test_user.email, test_user.token_version or 0)

    first = client_no_auth.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "NewPassword456"},
    )
    assert first.status_code == 200

    second = client_no_auth.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "SomeOtherPassword789"},
    )
    assert second.status_code == 400


def test_login_sets_access_token_cookie(client_no_auth, test_user):
    response = client_no_auth.post(
        "/auth/token",
        data={"username": "testuser", "password": "password"},
    )
    assert response.status_code == 200
    assert "access_token" in response.cookies


def test_login_rate_limited_after_5_attempts(client_no_auth):
    for _ in range(5):
        client_no_auth.post(
            "/auth/token",
            data={"username": "nobody", "password": "wrong"},
        )

    response = client_no_auth.post(
        "/auth/token",
        data={"username": "nobody", "password": "wrong"},
    )
    assert response.status_code == 429


def test_register_rate_limited_after_3_attempts(client_no_auth):
    base = {
        "firstname": "Test",
        "lastname": "User",
        "email": "x@x.com",
        "username": "userx",
        "password": "password1!",
        "country_of_origin": "GB",
        "date_of_birth": "2000-01-01",
    }

    for i in range(3):
        client_no_auth.post(
            "/users/register",
            json={**base, "username": f"user_{i}", "email": f"u{i}@test.com"},
        )

    response = client_no_auth.post(
        "/users/register",
        json={**base, "username": "user_final", "email": "final@test.com"},
    )
    assert response.status_code == 429
