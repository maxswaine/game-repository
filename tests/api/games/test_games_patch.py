from models.game import GameUpdate
from tests.utils import valid_game_payload
from backend.db.tables import Game, GameEquipment, GameTheme

def test_patch_game_success(client, db):
    payload = valid_game_payload()
    post_resp = client.post("/games/", json=payload)
    assert post_resp.status_code == 201
    created_game = post_resp.json()
    game_id = created_game["id"]

    update_payload = {
        "name": "Updated Uno",
        "equipment": [{"equipment_name": "New Uno Deck"}],
        "themes": [{"theme_name": "Strategy"}, {"theme_name": "Party"}]
    }

    update_model = GameUpdate(**update_payload)
    patch_resp = client.patch(f"/games/{game_id}", json=update_model.model_dump())
    assert patch_resp.status_code == 200
    updated_game = patch_resp.json()

    assert updated_game["id"] == game_id
    assert updated_game["name"] == "Updated Uno"

    assert len(updated_game["equipment"]) == 1
    assert updated_game["equipment"][0]["equipment_name"] == "New Uno Deck"

    theme_names = {t["theme_name"] for t in updated_game["themes"]}
    assert theme_names == {"Strategy", "Party"}

    assert updated_game["contributor"]["id"] == created_game["contributor"]["id"]

    db_game = db.query(Game).filter(Game.id == game_id).first()
    assert db_game.name == "Updated Uno"

    db_equipment = db.query(GameEquipment).filter(GameEquipment.game_id == game_id).all()
    assert len(db_equipment) == 1
    assert db_equipment[0].equipment_name == "New Uno Deck"

    db_themes = db.query(GameTheme).filter(GameTheme.game_id == game_id).all()
    theme_names_db = {t.theme_name for t in db_themes}
    assert theme_names_db == {"Strategy", "Party"}