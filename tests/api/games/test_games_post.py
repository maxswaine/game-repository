from backend.models.enums.equipment_enum import GameEquipmentEnum
from backend.models.enums.game_theme_enum import GameThemeEnum
from tests.api.games.helper import create_game, upvote_game
from tests.conftest import client_with_auth
from tests.utils import valid_game_payload


def test_create_game_success(client_with_auth):
    payload = valid_game_payload()

    data = create_game(client_with_auth)
    assert data["id"] is not None
    assert data["name"] == payload["name"]
    assert data["game_type"] == payload["game_type"]
    assert data["age_rating"] == payload["age_rating"]
    assert data["player_count"]["min_players"] == 2
    assert data["player_count"]["max_players"] == 6

    assert len(data["equipment"]) == 1
    assert data["equipment"][0]["equipment_name"] == GameEquipmentEnum.standard_deck

    assert len(data["themes"]) == 2
    assert {t["theme_name"] for t in data["themes"]} == {GameThemeEnum.strategy, GameThemeEnum.logic}

    assert data["contributor"]["username"] is not None


def test_create_game_unauthorized(client_no_auth):
    response = client_no_auth.post("/games/", json=valid_game_payload())
    assert response.status_code == 401


def test_upvote_game(client_with_auth):
    game = create_game(client_with_auth)

    response = upvote_game(client_with_auth, game["id"])
    assert response.status_code == 200

    data = response.json()
    assert data["upvotes"] == 1
    assert data["downvotes"] == 0


def test_remove_upvote_game(client_with_auth):
    game = create_game(client_with_auth)

    upvote_game(client_with_auth, game["id"])
    response = upvote_game(client_with_auth, game["id"], remove=True)

    assert response.status_code == 200

    data = response.json()
    assert data["upvotes"] == 0
    assert data["downvotes"] == 0
    assert data["upvotes"] == 0
    assert data["downvotes"] == 0
