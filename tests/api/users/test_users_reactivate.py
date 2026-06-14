import uuid
from datetime import datetime, timezone, timedelta

from src.api.auth import _maybe_reactivate
from src.db.tables import User


HASHED_PASSWORD = "$2b$12$b/B6ENyF.s93r2xvNx5ksuVdh.819Wvs5Q/GaHQlpO/F11.TC.SXe"  # "password"


def _make_inactive_user(db, *, days_ago: int, email: str):
    user = User(
        id=str(uuid.uuid4()),
        firstname="React",
        lastname="Test",
        username=f"reactuser_{uuid.uuid4().hex[:8]}",
        email=email,
        hashed_password=HASHED_PASSWORD,
        is_active=False,
        deletion_requested_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        created_at=datetime.now(timezone.utc),
        last_updated=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_maybe_reactivate_within_window(db):
    user = _make_inactive_user(db, days_ago=5, email="oauth_react@example.com")

    result = _maybe_reactivate(user, db)

    assert result is True
    db.refresh(user)
    assert user.is_active is True
    assert user.deletion_requested_at is None


def test_maybe_reactivate_past_window(db):
    user = _make_inactive_user(db, days_ago=31, email="oauth_expired@example.com")

    result = _maybe_reactivate(user, db)

    assert result is False
    db.refresh(user)
    assert user.is_active is False


def test_maybe_reactivate_active_user(db, test_user):
    result = _maybe_reactivate(test_user, db)

    assert result is False
