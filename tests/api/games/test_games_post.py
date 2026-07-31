from src.models.enums.equipment_enum import GameEquipmentEnum
from src.models.enums.game_setting_enum import GameSettingEnum
from tests.api.games.helper import create_public_game, upvote_game
from tests.conftest import client_with_auth
from tests.utils import valid_public_game_payload


def test_create_game_rejects_description_over_150_chars(client_with_auth):
    payload = valid_public_game_payload(overrides={"description": "x" * 151})
    response = client_with_auth.post("/games/", json=payload)
    assert response.status_code == 422


def test_create_game_accepts_description_at_150_chars(client_with_auth, db):
    payload = valid_public_game_payload(overrides={"description": "x" * 150})
    response = client_with_auth.post("/games/", json=payload)
    assert response.status_code == 201


def test_create_game_rejects_rules_over_5000_chars(client_with_auth):
    payload = valid_public_game_payload(overrides={"rules": "x" * 5001})
    response = client_with_auth.post("/games/", json=payload)
    assert response.status_code == 422


def test_create_game_rejects_objective_over_2000_chars(client_with_auth, db):
    payload = valid_public_game_payload(overrides={"objective": "x" * 2001})
    response = client_with_auth.post("/games/", json=payload)
    assert response.status_code == 422


def test_create_game_rejects_setup_over_2000_chars(client_with_auth, db):
    payload = valid_public_game_payload(overrides={"setup": "x" * 2001})
    response = client_with_auth.post("/games/", json=payload)
    assert response.status_code == 422


def test_create_game_success(client_with_auth, db):
    payload = valid_public_game_payload()

    data = create_public_game(client_with_auth, db)
    assert data["id"] is not None
    assert data["name"] == payload["name"]
    assert data["game_type"] == payload["game_type"]
    assert data["player_count"]["min_players"] == 2
    assert data["player_count"]["max_players"] == 6

    assert len(data["equipment"]) == 1
    assert data["equipment"][0] == GameEquipmentEnum.standard_deck

    assert set(data["game_setting"]) == {GameSettingEnum.game_night.value, GameSettingEnum.competitive.value}

    assert data["contributor"]["username"] is not None


def test_create_game_unauthorized(client_no_auth, db):
    response = client_no_auth.post("/games/", json=valid_public_game_payload())
    assert response.status_code == 401


def test_create_game_with_valid_icon(client_with_auth, db):
    payload = valid_public_game_payload(overrides={"icon": "sports-esports"})
    response = client_with_auth.post("/games/", json=payload)
    assert response.status_code == 201
    assert response.json()["icon"] == "sports-esports"


def test_create_game_without_icon_defaults_to_none(client_with_auth, db):
    data = create_public_game(client_with_auth, db)
    assert data["icon"] is None


def test_create_game_rejects_unknown_icon(client_with_auth, db):
    payload = valid_public_game_payload(overrides={"icon": "not-a-real-icon"})
    response = client_with_auth.post("/games/", json=payload)
    assert response.status_code == 422


def test_upvote_game(client_with_auth, db):
    game = create_public_game(client_with_auth, db)

    response = upvote_game(client_with_auth, game["id"])
    assert response.status_code == 200

    data = response.json()
    assert data["upvotes"] == 1


def test_remove_upvote_game(client_with_auth, db):
    game = create_public_game(client_with_auth, db)

    upvote_game(client_with_auth, game["id"])
    response = upvote_game(client_with_auth, game["id"])  # second call toggles it off

    assert response.status_code == 200

    data = response.json()
    assert data["upvotes"] == 0
