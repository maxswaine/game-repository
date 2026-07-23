from unittest.mock import patch


def test_upload_url_happy(client_with_auth, test_user):
    with patch("src.api.avatar.storage.generate_quarantine_put", return_value="https://presigned-put"):
        resp = client_with_auth.post(
            "/users/me/avatar/upload-url", json={"content_type": "image/jpeg"}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["upload_url"] == "https://presigned-put"
    assert body["object_key"].startswith(f"users/{test_user.id}/")
    assert body["object_key"].endswith(".jpg")


def test_upload_url_bad_content_type(client_with_auth):
    resp = client_with_auth.post(
        "/users/me/avatar/upload-url", json={"content_type": "application/pdf"}
    )
    assert resp.status_code == 422


def test_upload_url_requires_auth(client_no_auth):
    resp = client_no_auth.post(
        "/users/me/avatar/upload-url", json={"content_type": "image/jpeg"}
    )
    assert resp.status_code == 401


def _register(client, object_key):
    return client.post("/users/me/avatar", json={"object_key": object_key})


def test_register_happy_sets_avatar_url(client_with_auth, test_user, db):
    key = f"users/{test_user.id}/abc.jpg"
    public = f"https://cdn.example.com/{key}"
    with patch("src.api.avatar.storage.head_quarantine", return_value={"size": 1000, "content_type": "image/jpeg"}), \
         patch("src.api.avatar.storage.generate_quarantine_get", return_value="https://get"), \
         patch("src.api.avatar.check_image", return_value=True), \
         patch("src.api.avatar.storage.copy_to_public") as copy_mock, \
         patch("src.api.avatar.storage.delete_quarantine") as delq_mock, \
         patch("src.api.avatar.storage.public_url_for", return_value=public):
        resp = _register(client_with_auth, key)
    assert resp.status_code == 200
    assert resp.json()["avatar_url"] == public
    copy_mock.assert_called_once_with(key)
    delq_mock.assert_called_once_with(key)

    db.refresh(test_user)
    assert test_user.avatar_url == public


def test_register_replacing_own_r2_avatar_deletes_old_object(client_with_auth, test_user, db):
    old_key = f"users/{test_user.id}/old.jpg"
    test_user.avatar_url = f"https://cdn.example.com/{old_key}"
    db.commit()

    new_key = f"users/{test_user.id}/new.jpg"
    with patch("src.api.avatar.R2_PUBLIC_URL", "https://cdn.example.com"), \
         patch("src.api.avatar.storage.head_quarantine", return_value={"size": 1000, "content_type": "image/jpeg"}), \
         patch("src.api.avatar.storage.generate_quarantine_get", return_value="https://get"), \
         patch("src.api.avatar.check_image", return_value=True), \
         patch("src.api.avatar.storage.copy_to_public"), \
         patch("src.api.avatar.storage.delete_quarantine"), \
         patch("src.api.avatar.storage.delete_public") as delp_mock, \
         patch("src.api.avatar.storage.public_url_for", return_value=f"https://cdn.example.com/{new_key}"):
        resp = _register(client_with_auth, new_key)
    assert resp.status_code == 200
    delp_mock.assert_called_once_with(old_key)


def test_register_replacing_oauth_avatar_does_not_delete(client_with_auth, test_user, db):
    test_user.avatar_url = "https://lh3.googleusercontent.com/a/old-google-avatar.jpg"
    db.commit()

    new_key = f"users/{test_user.id}/new.jpg"
    with patch("src.api.avatar.R2_PUBLIC_URL", "https://cdn.example.com"), \
         patch("src.api.avatar.storage.head_quarantine", return_value={"size": 1000, "content_type": "image/jpeg"}), \
         patch("src.api.avatar.storage.generate_quarantine_get", return_value="https://get"), \
         patch("src.api.avatar.check_image", return_value=True), \
         patch("src.api.avatar.storage.copy_to_public"), \
         patch("src.api.avatar.storage.delete_quarantine"), \
         patch("src.api.avatar.storage.delete_public") as delp_mock, \
         patch("src.api.avatar.storage.public_url_for", return_value=f"https://cdn.example.com/{new_key}"):
        resp = _register(client_with_auth, new_key)
    assert resp.status_code == 200
    delp_mock.assert_not_called()


def test_register_rejects_foreign_key_prefix(client_with_auth, test_user):
    resp = _register(client_with_auth, f"users/{test_user.id}-not-really/x.jpg")
    assert resp.status_code == 422


def test_register_missing_object(client_with_auth, test_user):
    with patch("src.api.avatar.storage.head_quarantine", return_value=None):
        resp = _register(client_with_auth, f"users/{test_user.id}/x.jpg")
    assert resp.status_code == 422


def test_register_oversized(client_with_auth, test_user):
    with patch("src.api.avatar.storage.head_quarantine", return_value={"size": 6 * 1024 * 1024, "content_type": "image/jpeg"}), \
         patch("src.api.avatar.storage.delete_quarantine") as delq_mock:
        resp = _register(client_with_auth, f"users/{test_user.id}/x.jpg")
    assert resp.status_code == 422
    delq_mock.assert_called_once()


def test_register_moderation_reject_deletes_quarantine_no_public_copy(client_with_auth, test_user):
    key = f"users/{test_user.id}/bad.jpg"
    with patch("src.api.avatar.storage.head_quarantine", return_value={"size": 1000, "content_type": "image/jpeg"}), \
         patch("src.api.avatar.storage.generate_quarantine_get", return_value="https://get"), \
         patch("src.api.avatar.check_image", return_value=False), \
         patch("src.api.avatar.storage.copy_to_public") as copy_mock, \
         patch("src.api.avatar.storage.delete_quarantine") as delq_mock:
        resp = _register(client_with_auth, key)
    assert resp.status_code == 422
    copy_mock.assert_not_called()
    delq_mock.assert_called_once_with(key)


def test_register_requires_auth(client_no_auth, test_user):
    resp = client_no_auth.post(
        "/users/me/avatar", json={"object_key": f"users/{test_user.id}/x.jpg"}
    )
    assert resp.status_code == 401


def test_remove_deletes_own_r2_avatar_and_clears(client_with_auth, test_user, db):
    key = f"users/{test_user.id}/old.jpg"
    test_user.avatar_url = f"https://cdn.example.com/{key}"
    db.commit()

    with patch("src.api.avatar.R2_PUBLIC_URL", "https://cdn.example.com"), \
         patch("src.api.avatar.storage.delete_public") as delp_mock:
        resp = client_with_auth.delete("/users/me/avatar")
    assert resp.status_code == 200
    assert resp.json()["avatar_url"] is None
    delp_mock.assert_called_once_with(key)

    db.refresh(test_user)
    assert test_user.avatar_url is None


def test_remove_oauth_avatar_no_delete_call(client_with_auth, test_user, db):
    test_user.avatar_url = "https://lh3.googleusercontent.com/a/old-google-avatar.jpg"
    db.commit()

    with patch("src.api.avatar.R2_PUBLIC_URL", "https://cdn.example.com"), \
         patch("src.api.avatar.storage.delete_public") as delp_mock:
        resp = client_with_auth.delete("/users/me/avatar")
    assert resp.status_code == 200
    assert resp.json()["avatar_url"] is None
    delp_mock.assert_not_called()


def test_remove_when_no_avatar_is_noop(client_with_auth, test_user):
    assert test_user.avatar_url is None
    with patch("src.api.avatar.storage.delete_public") as delp_mock:
        resp = client_with_auth.delete("/users/me/avatar")
    assert resp.status_code == 200
    assert resp.json()["avatar_url"] is None
    delp_mock.assert_not_called()


def test_remove_requires_auth(client_no_auth):
    resp = client_no_auth.delete("/users/me/avatar")
    assert resp.status_code == 401
