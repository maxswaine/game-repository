import itertools
from unittest.mock import patch

from src.db.tables import Game
from src.models.enums.equipment_enum import GameEquipmentEnum
from tests.utils import valid_public_game_payload

FAKE_VECTOR = [1.0] + [0.0] * 1535

_CREATE_PATCH_TARGET = "src.api.games.embed_text"
_SEARCH_PATCH_TARGET = "src.api.search.embed_text"

_name_counter = itertools.count()


def _create_game(client, db, equipment):
    payload = valid_public_game_payload(
        overrides={"equipment": equipment, "name": f"Test Game {next(_name_counter)}"}
    )
    with patch(_CREATE_PATCH_TARGET, return_value=FAKE_VECTOR):
        response = client.post("/games/?force=true", json=payload)
    assert response.status_code == 201
    data = response.json()
    db.query(Game).filter(Game.id == data["id"]).update({"status": "approved"})
    db.commit()
    return data


def _search(client, query, limit=20):
    with patch(_SEARCH_PATCH_TARGET, return_value=FAKE_VECTOR):
        response = client.post("/games/search/", json={"query": query, "limit": limit})
    assert response.status_code == 200
    return response.json()


def test_no_cards_excludes_card_games(client_with_auth, db):
    card_game = _create_game(client_with_auth, db, [GameEquipmentEnum.standard_deck.value])
    dice_game = _create_game(client_with_auth, db, [GameEquipmentEnum.six_sided_dice.value])

    results = _search(client_with_auth, "a game for 5 friends in a bar with no cards")

    ids = {g["id"] for g in results}
    assert card_game["id"] not in ids
    assert dice_game["id"] in ids


def test_without_dice_excludes_dice_games(client_with_auth, db):
    dice_game = _create_game(client_with_auth, db, [GameEquipmentEnum.multiple_dice.value])
    card_game = _create_game(client_with_auth, db, [GameEquipmentEnum.jokers.value])

    results = _search(client_with_auth, "quick party game without dice")

    ids = {g["id"] for g in results}
    assert dice_game["id"] not in ids
    assert card_game["id"] in ids


def test_multiple_negations_union_excluded_sets(client_with_auth, db):
    card_game = _create_game(client_with_auth, db, [GameEquipmentEnum.multiple_decks.value])
    dice_game = _create_game(client_with_auth, db, [GameEquipmentEnum.dice_cup.value])
    voice_game = _create_game(client_with_auth, db, [GameEquipmentEnum.voice.value])

    results = _search(client_with_auth, "game for friends, no cards and no dice")

    ids = {g["id"] for g in results}
    assert card_game["id"] not in ids
    assert dice_game["id"] not in ids
    assert voice_game["id"] in ids


def test_mentioning_cards_without_negation_is_unaffected(client_with_auth, db):
    card_game = _create_game(client_with_auth, db, [GameEquipmentEnum.standard_deck.value])

    results = _search(client_with_auth, "a card game for 4 players")

    ids = {g["id"] for g in results}
    assert card_game["id"] in ids


def test_blanket_no_equipment_still_takes_priority(client_with_auth, db):
    card_game = _create_game(client_with_auth, db, [GameEquipmentEnum.standard_deck.value])
    no_equipment_game = _create_game(client_with_auth, db, [GameEquipmentEnum.none.value])

    results = _search(client_with_auth, "party game with no equipment")

    ids = {g["id"] for g in results}
    assert card_game["id"] not in ids
    assert no_equipment_game["id"] in ids


def test_dont_have_any_excludes_equipment(client_with_auth, db):
    card_game = _create_game(client_with_auth, db, [GameEquipmentEnum.standard_deck.value])
    dice_game = _create_game(client_with_auth, db, [GameEquipmentEnum.six_sided_dice.value])

    results = _search(
        client_with_auth,
        "i am in the pub with 4 friends and we don't have any playing cards",
    )

    ids = {g["id"] for g in results}
    assert card_game["id"] not in ids
    assert dice_game["id"] in ids


def test_playing_cards_two_word_phrase_resolves(client_with_auth, db):
    card_game = _create_game(client_with_auth, db, [GameEquipmentEnum.improvised_cards.value])
    dice_game = _create_game(client_with_auth, db, [GameEquipmentEnum.six_sided_dice.value])

    results = _search(client_with_auth, "bar game with no playing cards")

    ids = {g["id"] for g in results}
    assert card_game["id"] not in ids
    assert dice_game["id"] in ids
