from src.models.enums.equipment_enum import GameEquipmentEnum
from src.models.enums.game_setting_enum import GameSettingEnum
from tests.api.games.helper import create_public_game, upvote_game
from tests.conftest import client_with_auth
from tests.utils import valid_public_game_payload


def test_create_game_success(client_with_auth):
    payload = valid_public_game_payload()

    data = create_public_game(client_with_auth)
    assert data["id"] is not None
    assert data["name"] == payload["name"]
    assert data["game_type"] == payload["game_type"]
    assert data["age_rating"] == payload["age_rating"]
    assert data["player_count"]["min_players"] == 2
    assert data["player_count"]["max_players"] == 6

    assert len(data["equipment"]) == 1
    assert data["equipment"][0] == GameEquipmentEnum.standard_deck

    assert set(data["game_setting"]) == {GameSettingEnum.game_night.value, GameSettingEnum.competitive.value}

    assert data["contributor"]["username"] is not None


def test_create_game_unauthorized(client_no_auth):
    response = client_no_auth.post("/games/", json=valid_public_game_payload())
    assert response.status_code == 401


def test_upvote_game(client_with_auth):
    game = create_public_game(client_with_auth)

    response = upvote_game(client_with_auth, game["id"])
    assert response.status_code == 200

    data = response.json()
    assert data["upvotes"] == 1


def test_remove_upvote_game(client_with_auth):
    game = create_public_game(client_with_auth)

    upvote_game(client_with_auth, game["id"])
    response = upvote_game(client_with_auth, game["id"])  # second call toggles it off

    assert response.status_code == 200

    data = response.json()
    assert data["upvotes"] == 0
