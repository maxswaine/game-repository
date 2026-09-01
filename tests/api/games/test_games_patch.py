import uuid

from src.db.tables import Game, GameEquipment, GameSetting
from tests.utils import valid_public_game_payload


def _seed_game_owned_by(db, contributor_id: str) -> Game:
    game = Game(
        id=str(uuid.uuid4()),
        name="Contributor's Game",
        description="desc",
        game_type="Card",
        min_players=2,
        max_players=6,
        duration="30-45 minutes",
        objective="win",
        setup="setup",
        rules="rules",
        is_public=True,
        status="approved",
        contributor_id=contributor_id,
    )
    db.add(game)
    db.commit()
    return game


def test_patch_game_success(client_with_auth, db):
    payload = valid_public_game_payload()
    post_resp = client_with_auth.post("/games/", json=payload)
    assert post_resp.status_code == 201
    created_game = post_resp.json()
    game_id = created_game["id"]

    update_payload = {
        "name": "Updated Uno",
        "equipment": ["UNO Deck"],
        "game_setting": ["Chill", "Party"]
    }
    patch_resp = client_with_auth.patch(f"/games/{game_id}", json=update_payload)

    if patch_resp.status_code != 201:
        print(f"Status: {patch_resp.status_code}")
        print(f"Response: {patch_resp.json()}")
    assert patch_resp.status_code == 200
    updated_game = patch_resp.json()

    assert updated_game["id"] == game_id
    assert updated_game["name"] == "Updated Uno"

    assert len(updated_game["equipment"]) == 1
    assert updated_game["equipment"][0] == "UNO Deck"

    assert set(updated_game["game_setting"]) == {"Chill", "Party"}

    assert updated_game["contributor"]["username"] == created_game["contributor"]["username"]

    db_game = db.query(Game).filter(Game.id == game_id).first()
    assert db_game.name == "Updated Uno"

    db_equipment = db.query(GameEquipment).filter(GameEquipment.game_id == game_id).all()
    assert len(db_equipment) == 1
    assert db_equipment[0].equipment_name == "UNO Deck"

    db_settings = db.query(GameSetting).filter(GameSetting.game_id == game_id).all()
    assert {s.setting_name for s in db_settings} == {"Chill", "Party"}


def test_patch_game_icon(client_with_auth, db):
    payload = valid_public_game_payload()
    post_resp = client_with_auth.post("/games/", json=payload)
    assert post_resp.status_code == 201
    game_id = post_resp.json()["id"]

    patch_resp = client_with_auth.patch(f"/games/{game_id}", json={"icon": "bolt"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["icon"] == "bolt"

    db_game = db.query(Game).filter(Game.id == game_id).first()
    assert db_game.icon == "bolt"


def test_patch_game_rejects_unknown_icon(client_with_auth):
    payload = valid_public_game_payload()
    post_resp = client_with_auth.post("/games/", json=payload)
    game_id = post_resp.json()["id"]

    patch_resp = client_with_auth.patch(f"/games/{game_id}", json={"icon": "not-a-real-icon"})
    assert patch_resp.status_code == 422


def test_patch_game_no_changes(client_with_auth, db):
    payload = valid_public_game_payload()
    post_resp = client_with_auth.post("/games/", json=payload)
    assert post_resp.status_code == 201
    created_game = post_resp.json()
    game_id = created_game["id"]

    patch_resp = client_with_auth.patch(f"/games/{game_id}", json={})
    assert patch_resp.status_code == 200
    updated_game = patch_resp.json()

    assert updated_game == created_game


def test_patch_game_rejects_non_owner(client_as_second_user, db, test_user):
    game = _seed_game_owned_by(db, test_user.id)

    patch_resp = client_as_second_user.patch(f"/games/{game.id}", json={"name": "Hijacked"})
    assert patch_resp.status_code == 401


def test_patch_game_allows_admin_for_any_game(client_as_admin, db, test_user):
    game = _seed_game_owned_by(db, test_user.id)

    patch_resp = client_as_admin.patch(f"/games/{game.id}", json={"rules": "Cleaned-up rules text"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["rules"] == "Cleaned-up rules text"

    db_game = db.query(Game).filter(Game.id == game.id).first()
    assert db_game.rules == "Cleaned-up rules text"
    assert db_game.contributor_id == test_user.id
