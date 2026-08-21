def test_version_returns_app_version_and_min_supported(client_no_auth):
    response = client_no_auth.get("/version")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "min_supported_app_version" in data


def test_version_min_supported_defaults_to_empty_string(client_no_auth):
    response = client_no_auth.get("/version")
    assert response.status_code == 200
    assert response.json()["min_supported_app_version"] == ""


def test_request_without_app_version_header_still_succeeds(client_no_auth):
    response = client_no_auth.get("/version")
    assert response.status_code == 200


def test_request_with_app_version_header_still_succeeds(client_no_auth):
    response = client_no_auth.get("/version", headers={"X-App-Version": "1.2.3"})
    assert response.status_code == 200
