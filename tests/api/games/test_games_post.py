from tests.utils import valid_game_payload

def test_create_game_success(client):
    response = client.post("/games/", json=valid_game_payload())

    assert response.status_code == 201
    data = response.json()

    assert data["name"] == "Uno"
    assert data["game_type"] == "card"
    assert data["age_rating"] == "7+"

    assert data["player_count"]["min_players"] == 2
    assert data["player_count"]["max_players"] == 10

    assert len(data["equipment"]) == 1
    assert data["equipment"][0]["equipment_name"] == "Uno deck"

    assert len(data["themes"]) == 2
    assert {t["theme_name"] for t in data["themes"]} == {
        "Family",
        "Strategy",
    }

    assert data["contributor"]["id"] is not None