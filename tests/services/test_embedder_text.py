"""The duplicate check embeds a GameCreate; the stored embedding embeds the saved Game row.

If those two texts differ, every cosine score the duplicate check produces is measured against
a differently-shaped corpus. This pins them together.
"""
from types import SimpleNamespace

from src.models.game_models.game import GameCreate
from src.services.embedder import build_game_text, build_game_text_from_create
from tests.utils import valid_public_game_payload


def _saved_row_from(payload: dict) -> SimpleNamespace:
    """The Game row the API writes for this payload, as build_game_text sees it."""
    return SimpleNamespace(
        name=payload["name"],
        description=payload["description"],
        game_type=payload["game_type"],
        min_players=payload["player_count"]["min_players"],
        max_players=payload["player_count"]["max_players"],
        duration=payload["duration"],
        difficulty=payload.get("difficulty"),
        setting_items=[
            SimpleNamespace(setting_name=s) for s in (payload.get("game_setting") or [])
        ],
        equipment_items=[
            SimpleNamespace(equipment_name=e) for e in (payload.get("equipment") or [])
        ],
        objective=payload["objective"],
        setup=payload["setup"],
        rules=payload["rules"],
    )


def test_create_text_matches_saved_row_text():
    payload = valid_public_game_payload()
    from_create = build_game_text_from_create(GameCreate(**payload))
    from_row = build_game_text(_saved_row_from(payload), aliases=payload.get("aliases") or [])
    assert from_create == from_row


def test_no_equipment_sentinel_is_not_dropped_on_one_side_only():
    payload = valid_public_game_payload(overrides={"equipment": ["No Equipment"]})
    from_create = build_game_text_from_create(GameCreate(**payload))
    assert "No Equipment" in from_create
    assert from_create == build_game_text(_saved_row_from(payload))


def test_aliases_reach_the_duplicate_check():
    """A submission naming the game it is also known as should match that game."""
    payload = valid_public_game_payload(overrides={"aliases": ["Kemps", "  "]})
    text = build_game_text_from_create(GameCreate(**payload))
    assert "Also known as: Kemps" in text
