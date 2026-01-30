from tests.api.games.helper import create_game
from tests.conftest import client_with_auth, client_no_auth
from tests.utils import valid_game_payload, valid_user_payload


def test_get_games_returns_list(client_with_auth, client_no_auth):
    # First, create a game
    created_game = create_game(client_with_auth)

    # Now, fetch all games
    get_response = client_no_auth.get("/games/")
    assert get_response.status_code == 200

    data = get_response.json()
    assert isinstance(data, list)
    assert len(data) >= 1  # At least the game we just created

    # Check that the game we created exists in the response
    game = data[0]
    assert game["name"] == created_game["name"]
    assert game["game_type"] == created_game["game_type"]
    assert game["age_rating"] == created_game["age_rating"]

    # Check player count
    assert game["player_count"]["min_players"] == created_game["player_count"]["min_players"]
    assert game["player_count"]["max_players"] == created_game["player_count"]["max_players"]

    # Check equipment and themes
    assert len(game["equipment"]) == len(created_game["equipment"])
    assert {e["equipment_name"] for e in game["equipment"]} == {e["equipment_name"] for e in created_game["equipment"]}

    assert len(game["themes"]) == len(created_game["themes"])
    assert {t["theme_name"] for t in game["themes"]} == {t["theme_name"] for t in created_game["themes"]}

    # Check contributor
    assert game["contributor"]["id"] == created_game["contributor"]["id"]
    assert game["contributor"]["username"] == created_game["contributor"]["username"]