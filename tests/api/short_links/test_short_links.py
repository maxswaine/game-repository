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
