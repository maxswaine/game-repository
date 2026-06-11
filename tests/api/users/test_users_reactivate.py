import uuid
from datetime import datetime, timezone, timedelta

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


def test_reactivate_within_window_returns_200_and_token(client_no_auth, db):
    user = _make_inactive_user(db, days_ago=5, email="react_valid@example.com")

    response = client_no_auth.post(
        "/users/reactivate",
        json={"email": "react_valid@example.com", "password": "password"},
    )

    assert response.status_code == 200
    assert "access_token" in response.json()
    db.refresh(user)
    assert user.is_active is True
    assert user.deletion_requested_at is None


def test_reactivate_after_30_days_returns_400(client_no_auth, db):
    _make_inactive_user(db, days_ago=31, email="react_expired@example.com")

    response = client_no_auth.post(
        "/users/reactivate",
        json={"email": "react_expired@example.com", "password": "password"},
    )

    assert response.status_code == 400


def test_reactivate_wrong_password_returns_400(client_no_auth, db):
    _make_inactive_user(db, days_ago=5, email="react_badpw@example.com")

    response = client_no_auth.post(
        "/users/reactivate",
        json={"email": "react_badpw@example.com", "password": "wrongpassword"},
    )

    assert response.status_code == 400


def test_reactivate_unknown_email_returns_400(client_no_auth):
    response = client_no_auth.post(
        "/users/reactivate",
        json={"email": "nobody@example.com", "password": "password"},
    )

    assert response.status_code == 400


def test_reactivate_active_user_returns_400(client_no_auth, test_user):
    response = client_no_auth.post(
        "/users/reactivate",
        json={"email": "test@example.com", "password": "password"},
    )

    assert response.status_code == 400
