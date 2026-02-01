from starlette.testclient import TestClient

from backend.api.users import get_current_user_optional
from backend.db.database import get_db
from backend.main import app
from tests.api.games.helper import create_public_game, create_private_game, get_user_token
from tests.conftest import client_with_auth, client_no_auth


def test_get_games_returns_list(client_with_auth, client_no_auth):
    created_game = create_public_game(client_with_auth)

    get_response = client_no_auth.get("/games/")
    assert get_response.status_code == 200

    data = get_response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    game = data[0]
    assert game["name"] == created_game["name"]
    assert game["game_type"] == created_game["game_type"]
    assert game["age_rating"] == created_game["age_rating"]

    assert game["player_count"]["min_players"] == created_game["player_count"]["min_players"]
    assert game["player_count"]["max_players"] == created_game["player_count"]["max_players"]

    assert len(game["equipment"]) == len(created_game["equipment"])
    assert {e["equipment_name"] for e in game["equipment"]} == {e["equipment_name"] for e in created_game["equipment"]}

    assert len(game["themes"]) == len(created_game["themes"])
    assert {t["theme_name"] for t in game["themes"]} == {t["theme_name"] for t in created_game["themes"]}

    assert game["contributor"]["username"] == created_game["contributor"]["username"]
    assert game["contributor"]["country_of_origin"] == created_game["contributor"]["country_of_origin"]


def test_get_private_game_valid(client_with_auth, db, test_user):
    created_game = create_private_game(client_with_auth)
    game_id = created_game["id"]

    user_login = {"username": "testuser", "password": "password"}
    token = get_user_token(client_with_auth, user_login)
    headers = {"Authorization": f"Bearer {token}"}

    get_response = client_with_auth.get(f"/games/{game_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json() is not None


def test_get_private_game_forbidden(client_with_auth, db, second_user):
    created_game = create_private_game(client_with_auth)
    game_id = created_game["id"]

    app.dependency_overrides.clear()

    def override_get_db():
        yield db

    def override_get_current_user_optional():
        return second_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional

    with TestClient(app) as client_as_second_user:
        resp = client_as_second_user.get(f"/games/{game_id}")
        assert resp.status_code == 403

    app.dependency_overrides.clear()
