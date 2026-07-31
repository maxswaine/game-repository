from unittest.mock import patch
from tests.api.games.helper import create_public_game
from tests.conftest import client_with_auth
from tests.utils import valid_public_game_payload

FAKE_VECTOR = [1.0] + [0.0] * 1535  # 1536-dim unit vector

_PATCH_TARGET = "src.api.games.embed_text"


def test_create_game_returns_409_when_similar_game_exists(client_with_auth, db):
    with patch(_PATCH_TARGET, return_value=FAKE_VECTOR):
        create_public_game(client_with_auth, db)  # existing game stored with FAKE_VECTOR embedding

        payload = valid_public_game_payload(overrides={"name": "Slightly Different Name"})
        response = client_with_auth.post("/games/", json=payload)

    assert response.status_code == 409
    body = response.json()
    assert body["detail"]["code"] == "potential_duplicate"
    assert len(body["detail"]["similar_games"]) >= 1


def test_create_game_with_force_bypasses_duplicate_check(client_with_auth, db):
    with patch(_PATCH_TARGET, return_value=FAKE_VECTOR):
        create_public_game(client_with_auth, db)

        payload = valid_public_game_payload(overrides={"name": "Slightly Different Name"})
        response = client_with_auth.post("/games/?force=true", json=payload)

    assert response.status_code == 201


def test_create_game_proceeds_when_no_similar_games(client_with_auth, db):
    different_vector = [0.0] * 1535 + [1.0]
    with patch(_PATCH_TARGET, return_value=different_vector):
        create_public_game(client_with_auth, db)

    with patch(_PATCH_TARGET, return_value=FAKE_VECTOR):
        payload = valid_public_game_payload(overrides={"name": "Unrelated Game"})
        response = client_with_auth.post("/games/", json=payload)

    assert response.status_code == 201


def test_duplicate_check_skipped_when_openai_unavailable(client_with_auth, db):
    create_public_game(client_with_auth, db)  # no embedding stored (OpenAI fails in test env)

    with patch(_PATCH_TARGET, side_effect=Exception("OpenAI down")):
        payload = valid_public_game_payload(overrides={"name": "New Game"})
        response = client_with_auth.post("/games/", json=payload)

    assert response.status_code == 201
