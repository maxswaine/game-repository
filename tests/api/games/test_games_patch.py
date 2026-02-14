from backend.db.tables import Game, GameEquipment, GameTheme
from tests.utils import valid_public_game_payload


def test_patch_game_success(client_with_auth, db):
    payload = valid_public_game_payload()
    post_resp = client_with_auth.post("/games/", json=payload)
    assert post_resp.status_code == 201
    created_game = post_resp.json()
    game_id = created_game["id"]

    update_payload = {
        "name": "Updated Uno",
        "equipment": [{"equipment_name": "UNO Deck"}],
        "themes": [{"theme_name": "Strategy"}, {"theme_name": "Endurance"}]
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
    assert updated_game["equipment"][0]["equipment_name"] == "UNO Deck"

    theme_names = {t["theme_name"] for t in updated_game["themes"]}
    assert theme_names == {"Strategy", "Endurance"}

    assert updated_game["contributor"]["username"] == created_game["contributor"]["username"]

    db_game = db.query(Game).filter(Game.id == game_id).first()
    assert db_game.name == "Updated Uno"

    db_equipment = db.query(GameEquipment).filter(GameEquipment.game_id == game_id).all()
    assert len(db_equipment) == 1
    assert db_equipment[0].equipment_name == "UNO Deck"

    db_themes = db.query(GameTheme).filter(GameTheme.game_id == game_id).all()
    theme_names_db = {t.theme_name for t in db_themes}
    assert theme_names_db == {"Strategy", "Endurance"}


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
