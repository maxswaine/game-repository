import uuid
from datetime import datetime, timezone, date, timedelta

import pytest
from fastapi.testclient import TestClient

from src.api.users import get_current_active_user, get_current_user_optional
from src.db.database import get_db
from src.db.tables import Game, GameEquipment, GameSetting, User
from src.main import app
from tests.utils import valid_public_game_payload


# ---------------------------------------------------------------------------
# Fixtures
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


def _make_game(db, contributor, game_type="Card", has_adult_content=False, settings=None):
    game = Game(
        id=str(uuid.uuid4()),
        name=f"Test Game {uuid.uuid4().hex[:6]}",
        description="A test game",
        game_type=game_type,
        min_players=2,
        max_players=6,
        duration="30-45 mins",
        objective="Win",
        setup="Set up",
        rules="Play",
        is_public=True,
        status="approved",
        is_whats_that_game_verified=False,
        has_adult_content=has_adult_content,
        upvotes=0,
        contributor_id=contributor.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(game)
    db.flush()
    db.add(GameEquipment(game_id=game.id, equipment_name="No Equipment"))
    for s in (settings or []):
        db.add(GameSetting(game_id=game.id, setting_name=s))
    db.commit()
    return game


def _client_as(db, user):
    def override_get_db():
        yield db

    def override_get_current_user_optional():
        return user

    def override_get_current_active_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user
    client = TestClient(app)
    return client


# ---------------------------------------------------------------------------
# detect_adult_content unit tests
# ---------------------------------------------------------------------------

def test_detect_adult_content_drinking_game_type():
    from src.utils.age_filter import detect_adult_content
    assert detect_adult_content("Drinking", [], "") is True


def test_detect_adult_content_adults_only_setting():
    from src.utils.age_filter import detect_adult_content
    assert detect_adult_content("Card", ["Adults Only"], "") is True


def test_detect_adult_content_drinking_required_setting():
    from src.utils.age_filter import detect_adult_content
    assert detect_adult_content("Card", ["Drinking Required"], "") is True


def test_detect_adult_content_drinking_optional_setting():
    from src.utils.age_filter import detect_adult_content
    assert detect_adult_content("Card", ["Drinking Optional"], "") is True


def test_detect_adult_content_spicy_setting():
    from src.utils.age_filter import detect_adult_content
    assert detect_adult_content("Card", ["Spicy"], "") is True


def test_detect_adult_content_drinking_keyword_in_rules():
    from src.utils.age_filter import detect_adult_content
    assert detect_adult_content("Card", [], "Everyone takes a drink when they lose") is True


def test_detect_adult_content_shot_keyword_in_rules():
    from src.utils.age_filter import detect_adult_content
    assert detect_adult_content("Card", [], "Loser takes a shot") is True


def test_detect_adult_content_strip_keyword_in_rules():
    from src.utils.age_filter import detect_adult_content
    assert detect_adult_content("Card", [], "Loser must strip an item of clothing") is True


def test_detect_adult_content_matches_keyword_suffix():
    # Regression: keywords were compiled with strict \b...\b, so a suffixed form
    # like "sips" never matched the bare keyword "sip".
    from src.utils.age_filter import detect_adult_content
    assert detect_adult_content("Card", [], "Player sips from their cup.") is True


def test_detect_adult_content_clean_family_game():
    from src.utils.age_filter import detect_adult_content
    assert detect_adult_content("Card", ["Family Friendly"], "Match the pairs as fast as you can") is False


# ---------------------------------------------------------------------------
# GET /games/ filter integration tests
# ---------------------------------------------------------------------------

def test_get_games_hides_adult_content_from_anonymous(db, client_no_auth, test_user):
    adult_game = _make_game(db, test_user, has_adult_content=True)
    ids = [g["id"] for g in client_no_auth.get("/games/").json()]
    assert adult_game.id not in ids


def test_get_games_hides_drinking_game_from_anonymous(db, client_no_auth, test_user):
    drinking_game = _make_game(db, test_user, has_adult_content=True)
    ids = [g["id"] for g in client_no_auth.get("/games/").json()]
    assert drinking_game.id not in ids


def test_get_games_shows_clean_game_to_anonymous(db, client_no_auth, test_user):
    clean_game = _make_game(db, test_user, has_adult_content=False)
    ids = [g["id"] for g in client_no_auth.get("/games/").json()]
    assert clean_game.id in ids


def test_get_games_shows_adult_content_to_adult_user(db, test_user):
    adult_user = _make_adult_user(db)
    adult_game = _make_game(db, test_user, has_adult_content=True)
    client = _client_as(db, adult_user)
    try:
        ids = [g["id"] for g in client.get("/games/").json()]
        assert adult_game.id in ids
    finally:
        app.dependency_overrides.clear()


def test_get_games_hides_adult_content_from_minor_user(db, test_user):
    minor_user = _make_minor_user(db)
    adult_game = _make_game(db, test_user, has_adult_content=True)
    client = _client_as(db, minor_user)
    try:
        ids = [g["id"] for g in client.get("/games/").json()]
        assert adult_game.id not in ids
    finally:
        app.dependency_overrides.clear()


def test_get_games_hides_drinking_game_from_minor_user(db, test_user):
    minor_user = _make_minor_user(db)
    drinking_game = _make_game(db, test_user, has_adult_content=True)
    client = _client_as(db, minor_user)
    try:
        ids = [g["id"] for g in client.get("/games/").json()]
        assert drinking_game.id not in ids
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /games/{id} direct link filter
# ---------------------------------------------------------------------------

def test_get_game_by_id_returns_403_for_adult_content_to_anonymous(db, client_no_auth, test_user):
    adult_game = _make_game(db, test_user, has_adult_content=True)
    response = client_no_auth.get(f"/games/{adult_game.id}")
    assert response.status_code == 403


def test_get_game_by_id_returns_game_to_adult_user(db, test_user):
    adult_user = _make_adult_user(db)
    adult_game = _make_game(db, test_user, has_adult_content=True)
    client = _client_as(db, adult_user)
    try:
        response = client.get(f"/games/{adult_game.id}")
        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /games/ sets has_adult_content flag
# ---------------------------------------------------------------------------

def test_post_game_with_drinking_type_flags_adult_content(client_with_auth, db):
    payload = valid_public_game_payload(overrides={"game_type": "Drinking"})
    response = client_with_auth.post("/games/", json=payload)
    assert response.status_code == 201
    game = db.query(Game).filter(Game.id == response.json()["id"]).first()
    assert game.has_adult_content is True


def test_post_game_with_drinking_rules_flags_adult_content(client_with_auth, db):
    payload = valid_public_game_payload(overrides={"rules": "Everyone takes a drink when they lose a round"})
    response = client_with_auth.post("/games/", json=payload)
    assert response.status_code == 201
    game = db.query(Game).filter(Game.id == response.json()["id"]).first()
    assert game.has_adult_content is True


def test_post_clean_game_does_not_flag_adult_content(client_with_auth, db):
    payload = valid_public_game_payload()
    response = client_with_auth.post("/games/", json=payload)
    assert response.status_code == 201
    game = db.query(Game).filter(Game.id == response.json()["id"]).first()
    assert game.has_adult_content is False
