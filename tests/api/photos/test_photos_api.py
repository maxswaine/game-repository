from unittest.mock import patch

from fastapi.testclient import TestClient

from src.main import app
from src.db.database import get_db
from src.api.users import get_current_active_user
from tests.api.games.helper import create_public_game


def _own_game(client_with_auth, db):
    return create_public_game(client_with_auth, db)


def _switch_user(db, user):
    """Clear overrides and re-point auth at `user` (None = unauthenticated)."""
    app.dependency_overrides.clear()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    if user is not None:
        app.dependency_overrides[get_current_active_user] = lambda: user


def test_upload_url_happy(client_with_auth, db):
    game = _own_game(client_with_auth, db)
    with patch("src.api.photos.storage.generate_quarantine_put", return_value="https://presigned-put"):
        resp = client_with_auth.post(
            f"/games/{game['id']}/photos/upload-url", json={"content_type": "image/jpeg"}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["upload_url"] == "https://presigned-put"
    assert body["object_key"].startswith(f"games/{game['id']}/")
    assert body["object_key"].endswith(".jpg")
    assert "public_url" not in body


def test_upload_url_bad_content_type(client_with_auth, db):
    game = _own_game(client_with_auth, db)
    resp = client_with_auth.post(
        f"/games/{game['id']}/photos/upload-url", json={"content_type": "application/pdf"}
    )
    assert resp.status_code == 422


def test_upload_url_requires_owner(client_with_auth, db, second_user):
    game = _own_game(client_with_auth, db)
    _switch_user(db, second_user)
    with TestClient(app) as other:
        resp = other.post(
            f"/games/{game['id']}/photos/upload-url", json={"content_type": "image/png"}
        )
    assert resp.status_code == 403
    app.dependency_overrides.clear()


def test_upload_url_requires_auth(client_with_auth, db):
    game = _own_game(client_with_auth, db)
    _switch_user(db, None)
    with TestClient(app) as anon:
        resp = anon.post(
            f"/games/{game['id']}/photos/upload-url", json={"content_type": "image/png"}
        )
    assert resp.status_code == 401
    app.dependency_overrides.clear()


def _register(client, game_id, object_key):
    return client.post(f"/games/{game_id}/photos", json={"object_key": object_key})


def test_register_happy_copies_and_becomes_cover(client_with_auth, db):
    game = _own_game(client_with_auth, db)
    key = f"games/{game['id']}/abc.jpg"
    public = f"https://cdn.example.com/{key}"
    with patch("src.api.photos.storage.head_quarantine", return_value={"size": 1000, "content_type": "image/jpeg"}), \
         patch("src.api.photos.storage.generate_quarantine_get", return_value="https://get"), \
         patch("src.api.photos.check_image", return_value=True), \
         patch("src.api.photos.storage.copy_to_public") as copy_mock, \
         patch("src.api.photos.storage.delete_quarantine") as delq_mock, \
         patch("src.api.photos.storage.public_url_for", return_value=public):
        resp = _register(client_with_auth, game["id"], key)
    assert resp.status_code == 200
    body = resp.json()
    assert body["public_url"] == public
    assert body["position"] == 0
    copy_mock.assert_called_once_with(key)
    delq_mock.assert_called_once_with(key)

    got = client_with_auth.get(f"/games/{game['id']}").json()
    assert got["image_url"] == public
    assert len(got["photos"]) == 1


def test_register_rejects_foreign_key_prefix(client_with_auth, db):
    game = _own_game(client_with_auth, db)
    resp = _register(client_with_auth, game["id"], "games/other-game/abc.jpg")
    assert resp.status_code == 422


def test_register_missing_object(client_with_auth, db):
    game = _own_game(client_with_auth, db)
    with patch("src.api.photos.storage.head_quarantine", return_value=None):
        resp = _register(client_with_auth, game["id"], f"games/{game['id']}/x.jpg")
    assert resp.status_code == 422


def test_register_oversized(client_with_auth, db):
    game = _own_game(client_with_auth, db)
    with patch("src.api.photos.storage.head_quarantine", return_value={"size": 6 * 1024 * 1024, "content_type": "image/jpeg"}), \
         patch("src.api.photos.storage.delete_quarantine"):
        resp = _register(client_with_auth, game["id"], f"games/{game['id']}/x.jpg")
    assert resp.status_code == 422


def test_register_moderation_reject_deletes_quarantine_no_public_copy(client_with_auth, db):
    game = _own_game(client_with_auth, db)
    key = f"games/{game['id']}/bad.jpg"
    with patch("src.api.photos.storage.head_quarantine", return_value={"size": 1000, "content_type": "image/jpeg"}), \
         patch("src.api.photos.storage.generate_quarantine_get", return_value="https://get"), \
         patch("src.api.photos.check_image", return_value=False), \
         patch("src.api.photos.storage.copy_to_public") as copy_mock, \
         patch("src.api.photos.storage.delete_quarantine") as delq_mock:
        resp = _register(client_with_auth, game["id"], key)
    assert resp.status_code == 422
    copy_mock.assert_not_called()
    delq_mock.assert_called_once_with(key)


def test_register_requires_owner(client_with_auth, db, second_user):
    game = _own_game(client_with_auth, db)
    _switch_user(db, second_user)
    with TestClient(app) as other:
        resp = other.post(
            f"/games/{game['id']}/photos", json={"object_key": f"games/{game['id']}/x.jpg"}
        )
    assert resp.status_code == 403
    app.dependency_overrides.clear()


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


def test_cap_enforced_at_upload_url(client_with_auth, db):
    game = _own_game(client_with_auth, db)
    for i in range(10):
        _register_ok(client_with_auth, game["id"], f"p{i}")
    resp = client_with_auth.post(
        f"/games/{game['id']}/photos/upload-url", json={"content_type": "image/jpeg"}
    )
    assert resp.status_code == 409


def test_delete_repacks_and_resyncs_cover(client_with_auth, db):
    game = _own_game(client_with_auth, db)
    p0 = _register_ok(client_with_auth, game["id"], "first")
    p1 = _register_ok(client_with_auth, game["id"], "second")
    with patch("src.api.photos.storage.delete_public") as delp_mock:
        resp = client_with_auth.delete(f"/games/{game['id']}/photos/{p0['id']}")
    assert resp.status_code == 204
    delp_mock.assert_called_once()
    got = client_with_auth.get(f"/games/{game['id']}").json()
    assert len(got["photos"]) == 1
    assert got["photos"][0]["id"] == p1["id"]
    assert got["photos"][0]["position"] == 0
    assert got["image_url"] == p1["public_url"]


def test_delete_last_photo_clears_image_url(client_with_auth, db):
    game = _own_game(client_with_auth, db)
    p0 = _register_ok(client_with_auth, game["id"], "only")
    with patch("src.api.photos.storage.delete_public"):
        client_with_auth.delete(f"/games/{game['id']}/photos/{p0['id']}")
    got = client_with_auth.get(f"/games/{game['id']}").json()
    assert got["photos"] == []
    assert got["image_url"] is None


def test_reorder_sets_new_cover(client_with_auth, db):
    game = _own_game(client_with_auth, db)
    p0 = _register_ok(client_with_auth, game["id"], "a")
    p1 = _register_ok(client_with_auth, game["id"], "b")
    resp = client_with_auth.patch(
        f"/games/{game['id']}/photos/order", json={"photo_ids": [p1["id"], p0["id"]]}
    )
    assert resp.status_code == 200
    got = client_with_auth.get(f"/games/{game['id']}").json()
    assert [p["id"] for p in got["photos"]] == [p1["id"], p0["id"]]
    assert got["image_url"] == p1["public_url"]


def test_reorder_rejects_wrong_id_set(client_with_auth, db):
    game = _own_game(client_with_auth, db)
    p0 = _register_ok(client_with_auth, game["id"], "a")
    resp = client_with_auth.patch(
        f"/games/{game['id']}/photos/order", json={"photo_ids": [p0["id"], "not-a-real-id"]}
    )
    assert resp.status_code == 422
