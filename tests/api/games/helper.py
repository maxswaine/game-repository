from tests.utils import valid_public_game_payload, valid_private_game_payload


def create_public_game(client):
    payload = valid_public_game_payload()
    response = client.post("/games/", json=payload)
    assert response.status_code == 201
    return response.json()


def create_private_game(client):
    payload = valid_private_game_payload()
    response = client.post("/games/", json=payload)
    assert response.status_code == 201
    return response.json()


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


def upvote_game(client, game_id, remove: bool = False):
    url = f"/games/{game_id}/upvote"
    if remove:
        url += "?remove=true"
    return client.post(url)
