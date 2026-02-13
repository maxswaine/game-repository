from tests.conftest import client_no_auth
from tests.utils import valid_public_game_payload


def test_add_favourite_success(client_with_auth):
    game_response = client_with_auth.post("/games/", json=valid_public_game_payload())
    assert game_response.status_code == 201
    game_id = game_response.json()["id"]

    response = client_with_auth.post(f"/favourites/{game_id}")
    assert response.status_code == 201
    data = response.json()
    assert data["game_id"] == game_id
    assert data["user_id"] is not None


def test_add_favourite_game_not_found(client_with_auth):
    fake_game_id = "00000000-0000-0000-0000-000000000000"
    response = client_with_auth.post(f"/favourites/{fake_game_id}")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_add_favourite_already_favourited(client_with_auth):
    game_response = client_with_auth.post("/games/", json=valid_public_game_payload())
    game_id = game_response.json()["id"]

    response1 = client_with_auth.post(f"/favourites/{game_id}")
    assert response1.status_code == 201

    response2 = client_with_auth.post(f"/favourites/{game_id}")
    assert response2.status_code == 400
    assert "already favourited" in response2.json()["detail"].lower()


def test_add_favourite_unauthorized(client_no_auth):
    response = client_no_auth.post("/favourites/some-game-id")
    assert response.status_code == 401


def test_get_favourites_empty(client_with_auth):
    response = client_with_auth.get("/favourites/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_get_favourites_with_games(client_with_auth):
    game1_response = client_with_auth.post("/games/", json=valid_public_game_payload({"name": "Game 1"}))
    game1_id = game1_response.json()["id"]

    game2_response = client_with_auth.post("/games/", json=valid_public_game_payload({"name": "Game 2"}))
    game2_id = game2_response.json()["id"]

    client_with_auth.post(f"/favourites/{game1_id}")
    client_with_auth.post(f"/favourites/{game2_id}")

    response = client_with_auth.get("/favourites/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    game_names = {game["name"] for game in data}
    assert "Game 1" in game_names
    assert "Game 2" in game_names

    for game in data:
        assert game["id"] is not None
        assert game["name"] is not None
        assert game["equipment"] is not None
        assert game["themes"] is not None
        assert game["contributor"] is not None


def test_get_favourites_pagination(client_with_auth):
    for i in range(5):
        game_response = client_with_auth.post("/games/", json=valid_public_game_payload({"name": f"Game {i}"}))
        game_id = game_response.json()["id"]
        client_with_auth.post(f"/favourites/{game_id}")

    response = client_with_auth.get("/favourites/?limit=3&offset=0")
    assert response.status_code == 200
    assert len(response.json()) == 3

    response = client_with_auth.get("/favourites/?limit=3&offset=3")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_favourites_unauthorized(client_no_auth):
    response = client_no_auth.get("/favourites/")
    assert response.status_code == 401


def test_remove_favourite_success(client_with_auth):
    game_response = client_with_auth.post("/games/", json=valid_public_game_payload())
    game_id = game_response.json()["id"]
    client_with_auth.post(f"/favourites/{game_id}")

    response = client_with_auth.get("/favourites/")
    assert len(response.json()) == 1

    response = client_with_auth.delete(f"/favourites/{game_id}")
    assert response.status_code == 204

    response = client_with_auth.get("/favourites/")
    assert len(response.json()) == 0


def test_remove_favourite_not_found(client_with_auth):
    game_response = client_with_auth.post("/games/", json=valid_public_game_payload())
    game_id = game_response.json()["id"]

    response = client_with_auth.delete(f"/favourites/{game_id}")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_remove_favourite_unauthorized(client_no_auth):
    response = client_no_auth.delete("/favourites/some-game-id")
    assert response.status_code == 401
