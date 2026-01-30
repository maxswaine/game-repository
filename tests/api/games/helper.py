from tests.utils import valid_game_payload


def create_game(client):
    payload = valid_game_payload()
    response = client.post("/games/", json=payload)
    assert response.status_code == 201
    return response.json()


def upvote_game(client, game_id, remove: bool = False):
    url = f"/games/{game_id}/upvote"
    if remove:
        url += "?remove=true"
    return client.post(url)
