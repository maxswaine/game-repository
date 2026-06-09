import uuid
from datetime import datetime, timezone

from src.db.tables import User


def _make_user(db, username):
    user = User(
        id=str(uuid.uuid4()),
        firstname="Test",
        lastname="User",
        username=username,
        email=f"{username}@example.com",
        hashed_password="x",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    return user


def test_generate_unique_username_returns_base_when_free(db):
    from src.api.auth import generate_unique_username
    result = generate_unique_username(db, "brandnewuser")
    assert result == "brandnewuser"


def test_generate_unique_username_appends_suffix_when_taken(db):
    from src.api.auth import generate_unique_username
    _make_user(db, "john")
    result = generate_unique_username(db, "john")
    assert result == "john_2"


def test_generate_unique_username_increments_until_free(db):
    from src.api.auth import generate_unique_username
    _make_user(db, "jane")
    _make_user(db, "jane_2")
    result = generate_unique_username(db, "jane")
    assert result == "jane_3"
