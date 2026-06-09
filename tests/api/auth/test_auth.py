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
