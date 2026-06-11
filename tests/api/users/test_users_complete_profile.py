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
