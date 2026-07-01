import uuid
from datetime import datetime, timezone, date, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.users import get_current_active_user, get_current_user_optional
from src.db.database import get_db
from src.db.tables import User
from src.main import app
from tests.utils import valid_public_game_payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_adult_user(db):
    dob = (date.today() - timedelta(days=365 * 20)).isoformat()
    user = User(
        id=str(uuid.uuid4()),
        firstname="Adult",
        lastname="User",
        username=f"adultuser_{uuid.uuid4().hex[:6]}",
        email=f"adult_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="x",
        date_of_birth=dob,
        country_of_origin="GB",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    return user


def _make_minor_user(db):
    dob = (date.today() - timedelta(days=365 * 16)).isoformat()
    user = User(
        id=str(uuid.uuid4()),
        firstname="Minor",
        lastname="User",
        username=f"minoruser_{uuid.uuid4().hex[:6]}",
        email=f"minor_{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="x",
        date_of_birth=dob,
        country_of_origin="GB",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    return user


def _client_as(db, user):
    def override_get_db():
        yield db

    def override_current_user_optional():
        return user

    def override_current_active_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_optional] = override_current_user_optional
    app.dependency_overrides[get_current_active_user] = override_current_active_user
    return TestClient(app)


# ---------------------------------------------------------------------------
# detect_profanity — unit tests
# ---------------------------------------------------------------------------

def test_detect_profanity_explicit_word():
    from src.utils.age_filter import detect_profanity
    assert detect_profanity("what the fuck is going on") is True


def test_detect_profanity_leet_speak_wh0re():
    from src.utils.age_filter import detect_profanity
    assert detect_profanity("wh0re rules apply") is True


def test_detect_profanity_leet_speak_sh1t():
    from src.utils.age_filter import detect_profanity
    assert detect_profanity("oh sh1t") is True


def test_detect_profanity_cockroach_no_false_positive():
    from src.utils.age_filter import detect_profanity
    assert detect_profanity("there was a cockroach in the corner") is False


def test_detect_profanity_assassin_no_false_positive():
    from src.utils.age_filter import detect_profanity
    assert detect_profanity("the assassin must eliminate all targets") is False


def test_detect_profanity_classic_no_false_positive():
    from src.utils.age_filter import detect_profanity
    assert detect_profanity("a classic party game for all the family") is False


def test_detect_profanity_clean_text():
    from src.utils.age_filter import detect_profanity
    assert detect_profanity("take turns drawing cards and matching pairs") is False


def test_detect_profanity_word_in_family_safe_context():
    from src.utils.age_filter import detect_profanity
    assert detect_profanity("scunthorpe is a town in england") is False


# ---------------------------------------------------------------------------
# P5-b — Under-18 cannot submit explicit games
# ---------------------------------------------------------------------------

def test_minor_cannot_submit_game_with_profanity(db):
    minor_user = _make_minor_user(db)
    client = _client_as(db, minor_user)
    payload = valid_public_game_payload(overrides={"rules": "Loser must say 'what the fuck' out loud"})
    try:
        response = client.post("/games/", json=payload)
        assert response.status_code == 422
        assert "18" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_minor_cannot_submit_game_with_leet_profanity(db):
    minor_user = _make_minor_user(db)
    client = _client_as(db, minor_user)
    payload = valid_public_game_payload(overrides={"description": "wh0re rules apply to the loser"})
    try:
        response = client.post("/games/", json=payload)
        assert response.status_code == 422
        assert "18" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_minor_cannot_submit_game_with_sexual_content(db):
    minor_user = _make_minor_user(db)
    client = _client_as(db, minor_user)
    payload = valid_public_game_payload(overrides={"rules": "The loser must strip an item of clothing"})
    try:
        response = client.post("/games/", json=payload)
        assert response.status_code == 422
        assert "18" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_minor_cannot_patch_game_to_add_profanity(db):
    minor_user = _make_minor_user(db)
    client = _client_as(db, minor_user)
    try:
        with patch("src.api.games.check_content", return_value=True):
            create_resp = client.post("/games/", json=valid_public_game_payload())
        assert create_resp.status_code == 201
        game_id = create_resp.json()["id"]

        response = client.patch(f"/games/{game_id}", json={"rules": "Losers must say 'what the fuck'"})
        assert response.status_code == 422
        assert "18" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_adult_submitted_profane_game_hidden_from_minors(db):
    adult_user = _make_adult_user(db)
    minor_user = _make_minor_user(db)
    adult_client = _client_as(db, adult_user)
    try:
        with patch("src.api.games.check_content", return_value=True):
            resp = adult_client.post("/games/", json=valid_public_game_payload(
                overrides={"rules": "Loser must say 'what the fuck' out loud"}
            ))
        assert resp.status_code == 201
        game_id = resp.json()["id"]
    finally:
        app.dependency_overrides.clear()

    minor_client = _client_as(db, minor_user)
    try:
        ids = [g["id"] for g in minor_client.get("/games/").json()]
        assert game_id not in ids
    finally:
        app.dependency_overrides.clear()


def test_adult_can_submit_game_with_profanity(db):
    adult_user = _make_adult_user(db)
    client = _client_as(db, adult_user)
    payload = valid_public_game_payload(overrides={"rules": "Loser must say 'what the fuck' out loud"})
    try:
        with patch("src.api.games.check_content", return_value=True):
            response = client.post("/games/", json=payload)
        assert response.status_code == 201
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# P5-a — Global hate gate: POST /games/
# ---------------------------------------------------------------------------

def test_post_game_hate_content_returns_422_for_all_users(client_with_auth):
    with patch("src.api.games.check_content", return_value=False):
        response = client_with_auth.post("/games/", json=valid_public_game_payload())
    assert response.status_code == 422
    assert "community guidelines" in response.json()["detail"].lower()


def test_post_game_clean_content_passes_moderation(client_with_auth):
    with patch("src.api.games.check_content", return_value=True):
        response = client_with_auth.post("/games/", json=valid_public_game_payload())
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# P5-a — Global hate gate: PATCH /games/{id}
# ---------------------------------------------------------------------------

def test_patch_game_hate_content_returns_422(client_with_auth):
    with patch("src.api.games.check_content", return_value=True):
        create_resp = client_with_auth.post("/games/", json=valid_public_game_payload())
    game_id = create_resp.json()["id"]

    with patch("src.api.games.check_content", return_value=False):
        response = client_with_auth.patch(f"/games/{game_id}", json={"description": "flagged content"})
    assert response.status_code == 422
    assert "community guidelines" in response.json()["detail"].lower()


def test_patch_game_non_text_field_skips_moderation(client_with_auth):
    with patch("src.api.games.check_content", return_value=True):
        create_resp = client_with_auth.post("/games/", json=valid_public_game_payload())
    game_id = create_resp.json()["id"]

    with patch("src.api.games.check_content") as mock_mod:
        response = client_with_auth.patch(f"/games/{game_id}", json={"is_public": False})
    mock_mod.assert_not_called()
    assert response.status_code == 200
