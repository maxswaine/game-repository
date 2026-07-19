import pytest


def test_create_short_link_model_validates_code_and_url():
    from src.models.short_link_models.short_link import ShortLinkCreate

    ok = ShortLinkCreate(code="poster1", target_url="https://example.com/dl")
    assert ok.code == "poster1"
    assert ok.label is None

    with pytest.raises(ValueError):
        ShortLinkCreate(code="bad code!", target_url="https://example.com")

    with pytest.raises(ValueError):
        ShortLinkCreate(code="poster1", target_url="ftp://example.com")


def test_short_link_table_row_roundtrips(db):
    from src.db.tables import ShortLink

    row = ShortLink(code="poster1", target_url="https://example.com/dl")
    db.add(row)
    db.commit()
    db.refresh(row)

    assert row.is_active is True
    assert row.scan_count == 0
    assert row.created_at is not None


def _seed_link(db, code="poster1", target="https://example.com/dl", active=True):
    from src.db.tables import ShortLink
    row = ShortLink(code=code, target_url=target, is_active=active)
    db.add(row)
    db.commit()
    return row


def test_redirect_active_code_returns_302(client_no_auth, db):
    _seed_link(db)
    response = client_no_auth.get("/qr/poster1", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/dl"


def test_redirect_increments_scan_count(client_no_auth, db):
    from src.db.tables import ShortLink
    _seed_link(db)
    client_no_auth.get("/qr/poster1", follow_redirects=False)
    client_no_auth.get("/qr/poster1", follow_redirects=False)
    row = db.query(ShortLink).filter(ShortLink.code == "poster1").first()
    assert row.scan_count == 2


def test_redirect_inactive_code_returns_404(client_no_auth, db):
    _seed_link(db, code="dead", active=False)
    response = client_no_auth.get("/qr/dead", follow_redirects=False)
    assert response.status_code == 404


def test_redirect_missing_code_returns_404(client_no_auth):
    response = client_no_auth.get("/qr/nonexistent", follow_redirects=False)
    assert response.status_code == 404


def test_admin_create_link_returns_201(client_as_admin):
    response = client_as_admin.post(
        "/admin/links",
        json={"code": "freshers25", "target_url": "https://example.com/dl", "label": "Freshers"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["code"] == "freshers25"
    assert data["scan_count"] == 0
    assert data["is_active"] is True


def test_admin_create_duplicate_code_returns_409(client_as_admin):
    payload = {"code": "dup1", "target_url": "https://example.com"}
    client_as_admin.post("/admin/links", json=payload)
    response = client_as_admin.post("/admin/links", json=payload)
    assert response.status_code == 409


def test_admin_create_bad_url_returns_422(client_as_admin):
    response = client_as_admin.post(
        "/admin/links", json={"code": "x1", "target_url": "notaurl"}
    )
    assert response.status_code == 422


def test_admin_create_bad_code_returns_422(client_as_admin):
    response = client_as_admin.post(
        "/admin/links", json={"code": "bad code!", "target_url": "https://example.com"}
    )
    assert response.status_code == 422


def test_admin_list_links(client_as_admin):
    client_as_admin.post(
        "/admin/links", json={"code": "listme", "target_url": "https://example.com"}
    )
    response = client_as_admin.get("/admin/links")
    assert response.status_code == 200
    assert any(link["code"] == "listme" for link in response.json())


def test_admin_patch_target_url(client_as_admin):
    client_as_admin.post(
        "/admin/links", json={"code": "patch1", "target_url": "https://old.com"}
    )
    response = client_as_admin.patch(
        "/admin/links/patch1", json={"target_url": "https://new.com"}
    )
    assert response.status_code == 200
    assert response.json()["target_url"] == "https://new.com"


def test_admin_patch_deactivate_then_redirect_404(client_as_admin, client_no_auth):
    client_as_admin.post(
        "/admin/links", json={"code": "kill1", "target_url": "https://example.com"}
    )
    client_as_admin.patch("/admin/links/kill1", json={"is_active": False})
    response = client_no_auth.get("/qr/kill1", follow_redirects=False)
    assert response.status_code == 404


def test_admin_patch_missing_returns_404(client_as_admin):
    response = client_as_admin.patch(
        "/admin/links/ghost", json={"target_url": "https://example.com"}
    )
    assert response.status_code == 404


def test_admin_delete_link(client_as_admin, client_no_auth):
    client_as_admin.post(
        "/admin/links", json={"code": "del1", "target_url": "https://example.com"}
    )
    delete = client_as_admin.delete("/admin/links/del1")
    assert delete.status_code == 204
    redirect = client_no_auth.get("/qr/del1", follow_redirects=False)
    assert redirect.status_code == 404


def test_admin_delete_missing_returns_404(client_as_admin):
    response = client_as_admin.delete("/admin/links/ghost")
    assert response.status_code == 404


def test_non_admin_cannot_create_link(client_with_auth):
    response = client_with_auth.post(
        "/admin/links", json={"code": "nope", "target_url": "https://example.com"}
    )
    assert response.status_code == 403
