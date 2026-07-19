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
