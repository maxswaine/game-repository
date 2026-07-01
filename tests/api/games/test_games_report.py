import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.users import get_current_active_user, get_current_user_optional
from src.db.database import get_db
from src.db.tables import Game, GameEquipment, GameReport, User
from src.main import app
from src.models.enums.report_reason_enum import GameReportReasonEnum


# ---------------------------------------------------------------------------
# Helpers — insert game directly into DB to avoid multi-client fixture conflicts
# ---------------------------------------------------------------------------

def _make_game(db, contributor):
    game = Game(
        id=str(uuid.uuid4()),
        name="Reportable Game",
        description="A game to be reported",
        game_type="Card",
        min_players=2,
        max_players=6,
        duration="30-45 mins",
        objective="Win",
        setup="Set up",
        rules="Play",
        is_public=True,
        is_whats_that_game_verified=False,
        has_adult_content=False,
        upvotes=0,
        contributor_id=contributor.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(game)
    db.flush()
    db.add(GameEquipment(game_id=game.id, equipment_name="No Equipment"))
    db.commit()
    return game


def _client_as(db, user):
    def override_get_db():
        yield db

    def override_current_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_optional] = override_current_user
    app.dependency_overrides[get_current_active_user] = override_current_user
    return TestClient(app)


def _report_payload(reason=GameReportReasonEnum.inappropriate_content):
    return {"reason": reason.value}


# ---------------------------------------------------------------------------
# Success
# ---------------------------------------------------------------------------

def test_report_game_returns_201(db, test_user, second_user):
    game = _make_game(db, test_user)
    client = _client_as(db, second_user)
    try:
        response = client.post(f"/games/{game.id}/report", json=_report_payload())
        assert response.status_code == 201
    finally:
        app.dependency_overrides.clear()


def test_report_game_saves_to_db(db, test_user, second_user):
    game = _make_game(db, test_user)
    client = _client_as(db, second_user)
    try:
        client.post(f"/games/{game.id}/report", json=_report_payload())
        report = db.query(GameReport).filter(GameReport.game_id == game.id).first()
        assert report is not None
        assert report.reason == GameReportReasonEnum.inappropriate_content.value
        assert report.status == "pending"
    finally:
        app.dependency_overrides.clear()


def test_report_game_response_body(db, test_user, second_user):
    game = _make_game(db, test_user)
    client = _client_as(db, second_user)
    try:
        response = client.post(f"/games/{game.id}/report", json=_report_payload())
        assert "message" in response.json()
    finally:
        app.dependency_overrides.clear()


def test_report_game_all_valid_reasons_accepted(db, test_user, second_user):
    game = _make_game(db, test_user)
    client = _client_as(db, second_user)
    try:
        seen = set()
        for reason in GameReportReasonEnum:
            response = client.post(f"/games/{game.id}/report", json={"reason": reason.value})
            # First attempt 201, subsequent are 400 (already reported)
            assert response.status_code in (201, 400)
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth required
# ---------------------------------------------------------------------------

def test_report_game_requires_auth(db, test_user, client_no_auth):
    game = _make_game(db, test_user)
    response = client_no_auth.post(f"/games/{game.id}/report", json=_report_payload())
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Cannot report own game
# ---------------------------------------------------------------------------

def test_report_own_game_returns_400(db, test_user):
    game = _make_game(db, test_user)
    client = _client_as(db, test_user)
    try:
        response = client.post(f"/games/{game.id}/report", json=_report_payload())
        assert response.status_code == 400
        assert "own" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Duplicate report
# ---------------------------------------------------------------------------

def test_duplicate_report_returns_400(db, test_user, second_user):
    game = _make_game(db, test_user)
    client = _client_as(db, second_user)
    try:
        client.post(f"/games/{game.id}/report", json=_report_payload())
        response = client.post(f"/games/{game.id}/report", json=_report_payload())
        assert response.status_code == 400
        assert "already" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_report_missing_reason_returns_422(db, test_user, second_user):
    game = _make_game(db, test_user)
    client = _client_as(db, second_user)
    try:
        response = client.post(f"/games/{game.id}/report", json={})
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_report_invalid_reason_returns_422(db, test_user, second_user):
    game = _make_game(db, test_user)
    client = _client_as(db, second_user)
    try:
        response = client.post(f"/games/{game.id}/report", json={"reason": "NotARealReason"})
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Not found
# ---------------------------------------------------------------------------

def test_report_nonexistent_game_returns_404(db, second_user):
    client = _client_as(db, second_user)
    try:
        response = client.post("/games/nonexistent-id/report", json=_report_payload())
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
