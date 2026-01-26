from __future__ import annotations

def valid_game_payload(overrides: dict | None = None):
    payload = {
        "name": "Uno",
        "description": "A classic card game",
        "age_rating": "7+",
        "game_type": "card",
        "player_count": {
            "min_players": 2,
            "max_players": 10
        },
        "duration": "30 minutes",
        "equipment": [
            {"equipment_name": "Uno deck"}
        ],
        "themes": [
            {"theme_name": "Family"},
            {"theme_name": "Strategy"}
        ],
        "rules": "Rules text",
        "image_url": "https://example.com/uno.jpg",
        "is_public": True,
    }

    if overrides:
        payload.update(overrides)

    return payload


def valid_user_payload(overrides: dict | None = None):
    payload = {
        "firstname": "Test",
        "lastname": "User",
        "email": "testuser@test.com",
        "username": "testuser1",
        "password": "testpassword1!",
        "country_of_origin": "UK"
    }

    if overrides:
        payload.update(overrides)

    return payload
