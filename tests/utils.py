from __future__ import annotations


def valid_game_payload(overrides: dict | None = None):
    payload = {
        "name": "Test Game",
        "description": "Test description",
        "age_rating": "7+",
        "game_type": "card",
        "player_count": {
            "min_players": 2,
            "max_players": 6
        },
        "duration": "30 minutes",
        "equipment": [
            {"equipment_name": "standard_deck"}
        ],
        "themes": [
            {"theme_name": "strategy"},
            {"theme_name": "logic"}
        ],
        "rules": "Some rules",
        "image_url": None,
        "is_public": True,
        "is_whats_that_game_certified": False
    }

    if overrides:
        payload.update(overrides)

    return payload


def valid_user_payload(overrides: dict | None = None):
    payload = {
        "firstname": "test",
        "lastname": "user",
        "email": "test@user.com",
        "username": "testuser123",
        "password": "testuser1!",
        "country_of_origin": "UK"
    }

    if overrides:
        payload.update(overrides)

    return payload
