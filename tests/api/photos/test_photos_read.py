from unittest.mock import patch

from tests.api.games.helper import create_public_game


def _register_ok(client, game_id, name):
    key = f"games/{game_id}/{name}.jpg"
    public = f"https://cdn.example.com/{key}"
    with patch("src.api.photos.storage.head_quarantine", return_value={"size": 1000, "content_type": "image/jpeg"}), \
         patch("src.api.photos.storage.generate_quarantine_get", return_value="https://get"), \
         patch("src.api.photos.check_image", return_value=True), \
         patch("src.api.photos.storage.copy_to_public"), \
         patch("src.api.photos.storage.delete_quarantine"), \
         patch("src.api.photos.storage.public_url_for", return_value=public):
        return client.post(f"/games/{game_id}/photos", json={"object_key": key}).json()


def test_game_read_lists_photos_in_order(client_with_auth):
    game = create_public_game(client_with_auth)
    p0 = _register_ok(client_with_auth, game["id"], "a")
    p1 = _register_ok(client_with_auth, game["id"], "b")

    got = client_with_auth.get(f"/games/{game['id']}").json()
    assert [p["id"] for p in got["photos"]] == [p0["id"], p1["id"]]
    assert [p["position"] for p in got["photos"]] == [0, 1]


def test_games_list_includes_photos(client_with_auth):
    game = create_public_game(client_with_auth)
    _register_ok(client_with_auth, game["id"], "a")
    listed = client_with_auth.get("/games/").json()
    match = next(g for g in listed if g["id"] == game["id"])
    assert len(match["photos"]) == 1
