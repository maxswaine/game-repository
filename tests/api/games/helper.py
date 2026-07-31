from src.db.tables import Game
from tests.utils import valid_public_game_payload, valid_private_game_payload


def _approve(db, game_id):
    db.query(Game).filter(Game.id == game_id).update({"status": "approved"})
    db.commit()


def create_public_game(client, db):
    payload = valid_public_game_payload()
    response = client.post("/games/", json=payload)
    assert response.status_code == 201
    data = response.json()
    _approve(db, data["id"])
    data["status"] = "approved"
    return data


def create_private_game(client, db):
    payload = valid_private_game_payload()
    response = client.post("/games/", json=payload)
    assert response.status_code == 201
    data = response.json()
    _approve(db, data["id"])
    data["status"] = "approved"
    return data


def create_user(client, payload):
    response = client.post("/users/register/", json=payload)

    assert response.status_code == 201
    return response.json()


def get_user_token(client, user_login) -> str:
    response = client.post(
        "/auth/token",
        data=user_login
    )

    assert response.status_code == 200
    token_data = response.json()
    assert "access_token" in token_data
    return token_data["access_token"]


def upvote_game(client, game_id):
    return client.post(f"/games/{game_id}/upvote")
