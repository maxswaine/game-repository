from __future__ import annotations

from backend.models.enums.age_rating_enum import AgeRatingEnum
from backend.models.enums.duration_enum import DurationEnum
from backend.models.enums.equipment_enum import GameEquipmentEnum
from backend.models.enums.game_theme_enum import GameThemeEnum
from backend.models.enums.game_type_enum import GameTypeEnum


def valid_public_game_payload(overrides: dict | None = None):
    payload = {
        "name": "Test Game",
        "description": "Test description",
        "age_rating": AgeRatingEnum.age_7.value,
        "game_type": GameTypeEnum.card.value,
        "player_count": {
            "min_players": 2,
            "max_players": 6
        },
        "duration": DurationEnum.thirty_to_45_min.value,
        "equipment": [
            {"equipment_name": GameEquipmentEnum.standard_deck.value}
        ],
        "themes": [
            {"theme_name": GameThemeEnum.strategy.value},
            {"theme_name": GameThemeEnum.logic.value}
        ],
        "objective": "Win the game",
        "setup": "Get some friends to play",
        "rules": "Some rules",
        "image_url": None,
        "is_public": True,
        "is_whats_that_game_certified": False
    }

    if overrides:
        payload.update(overrides)

    return payload


def valid_private_game_payload(overrides: dict | None = None):
    payload = {
        "name": "Test Game",
        "description": "Test description",
        "age_rating": AgeRatingEnum.age_7.value,
        "game_type": GameTypeEnum.card.value,
        "player_count": {
            "min_players": 2,
            "max_players": 6
        },
        "duration": DurationEnum.thirty_to_45_min.value,
        "equipment": [
            {"equipment_name": GameEquipmentEnum.standard_deck.value}
        ],
        "themes": [
            {"theme_name": GameThemeEnum.strategy.value},
            {"theme_name": GameThemeEnum.logic.value}
        ],
        "objective": "Win the game",
        "setup": "Get some friends to play",
        "rules": "Some rules",
        "image_url": None,
        "is_public": False,
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
        "country_of_origin": "UK",
        "date_of_birth": "2000-01-13"
    }

    if overrides:
        payload.update(overrides)

    return payload
