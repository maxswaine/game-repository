from unittest.mock import patch

from src.api.users import get_current_active_user, get_current_user_optional
from src.db.database import get_db
from src.db.tables import Game, GameReport
from src.main import app
from tests.api.games.helper import get_user_token
from tests.utils import valid_public_game_payload


def _client_as(db, user):
    from fastapi.testclient import TestClient

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_optional] = lambda: user
    app.dependency_overrides[get_current_active_user] = lambda: user
    return TestClient(app)


def _submit_pending_game(client_with_auth):
    with patch("src.api.games.GAME_REVIEW_GATE_ENABLED", True):
        response = client_with_auth.post("/games/", json=valid_public_game_payload())
    assert response.status_code == 201
    return response.json()


def _report_game(db, game_id, reporter_id, reason="Spam"):
    report = GameReport(game_id=game_id, reporter_id=reporter_id, reason=reason)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


class TestPendingGate:
    def test_new_game_defaults_to_pending_and_hidden_from_public_list(self, client_with_auth, client_no_auth):
        game = _submit_pending_game(client_with_auth)
        assert game["status"] == "pending"

        listed = client_no_auth.get("/games/").json()
        assert game["id"] not in {g["id"] for g in listed}

    def test_pending_game_hidden_from_anonymous_direct_get(self, client_with_auth, client_no_auth):
        game = _submit_pending_game(client_with_auth)
        response = client_no_auth.get(f"/games/{game['id']}")
        assert response.status_code == 403

    def test_owner_can_still_see_own_pending_game(self, client_with_auth):
        game = _submit_pending_game(client_with_auth)

        token = get_user_token(client_with_auth, {"username": "testuser", "password": "password"})
        response = client_with_auth.get(
            f"/games/{game['id']}", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

        mine = client_with_auth.get("/games/mine").json()
        assert game["id"] in {g["id"] for g in mine}

    def test_admin_can_view_any_pending_game_directly(self, db, client_with_auth, admin_user):
        game = _submit_pending_game(client_with_auth)
        try:
            admin_client = _client_as(db, admin_user)
            response = admin_client.get(f"/games/{game['id']}")
            assert response.status_code == 200
            assert response.json()["id"] == game["id"]
        finally:
            app.dependency_overrides.clear()

    def test_non_admin_still_403_on_others_pending_game(self, db, client_with_auth, client_as_second_user):
        game = _submit_pending_game(client_with_auth)
        response = client_as_second_user.get(f"/games/{game['id']}")
        assert response.status_code == 403


class TestAdminReviewQueue:
    def test_non_admin_cannot_list_pending(self, client_with_auth):
        response = client_with_auth.get("/admin/games/pending")
        assert response.status_code == 403

    def test_admin_sees_pending_game_in_queue(self, client_with_auth, client_as_admin):
        game = _submit_pending_game(client_with_auth)
        response = client_as_admin.get("/admin/games/pending")
        assert response.status_code == 200
        assert game["id"] in {g["id"] for g in response.json()}

    def test_approve_makes_game_publicly_visible(self, db, test_user, client_as_admin, client_no_auth):
        game = Game(
            id="game-approve-1",
            name="Approve Me",
            description="desc",
            game_type="Card",
            min_players=2,
            max_players=6,
            duration="30-45 minutes",
            objective="win",
            setup="setup",
            rules="rules",
            is_public=True,
            contributor_id=test_user.id,
        )
        db.add(game)
        db.commit()
        assert game.status == "pending"

        response = client_as_admin.patch(
            f"/admin/games/{game.id}/review", json={"status": "approved"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "approved"

        listed = client_no_auth.get("/games/").json()
        assert game.id in {g["id"] for g in listed}

    def test_reject_sets_reason_and_keeps_game_hidden(self, db, test_user, client_as_admin, client_no_auth):
        game = Game(
            id="game-reject-1",
            name="Reject Me",
            description="desc",
            game_type="Card",
            min_players=2,
            max_players=6,
            duration="30-45 minutes",
            objective="win",
            setup="setup",
            rules="rules",
            is_public=True,
            contributor_id=test_user.id,
        )
        db.add(game)
        db.commit()

        response = client_as_admin.patch(
            f"/admin/games/{game.id}/review",
            json={
                "status": "rejected",
                "rejection_reason_code": "Duplicate Submission",
                "rejection_reason": "Duplicate of an existing game",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "rejected"
        assert body["rejection_reason_code"] == "Duplicate Submission"
        assert body["rejection_reason"] == "Duplicate of an existing game"

        listed = client_no_auth.get("/games/").json()
        assert game.id not in {g["id"] for g in listed}

    def test_reject_without_reason_returns_422(self, client_with_auth, client_as_admin):
        game = _submit_pending_game(client_with_auth)
        response = client_as_admin.patch(
            f"/admin/games/{game['id']}/review", json={"status": "rejected"}
        )
        assert response.status_code == 422

    def test_invalid_status_returns_422(self, client_with_auth, client_as_admin):
        game = _submit_pending_game(client_with_auth)
        response = client_as_admin.patch(
            f"/admin/games/{game['id']}/review", json={"status": "banana"}
        )
        assert response.status_code == 422

    def test_missing_game_returns_404(self, client_as_admin):
        response = client_as_admin.patch(
            "/admin/games/does-not-exist/review", json={"status": "approved"}
        )
        assert response.status_code == 404


class TestReportResolution:
    def test_non_admin_cannot_list_reports(self, client_with_auth):
        response = client_with_auth.get("/admin/games/reports")
        assert response.status_code == 403

    def test_missing_report_returns_404(self, client_as_admin):
        response = client_as_admin.patch(
            "/admin/games/reports/does-not-exist", json={"action": "dismiss"}
        )
        assert response.status_code == 404

    def test_reject_without_reason_code_returns_422(self, db, test_user, second_user, client_as_admin):
        game = Game(
            id="game-report-noreason-1",
            name="Reported Game",
            description="desc",
            game_type="Card",
            min_players=2,
            max_players=6,
            duration="30-45 minutes",
            objective="win",
            setup="setup",
            rules="rules",
            is_public=True,
            status="approved",
            contributor_id=test_user.id,
        )
        db.add(game)
        db.commit()
        report = _report_game(db, game.id, second_user.id)

        response = client_as_admin.patch(
            f"/admin/games/reports/{report.id}", json={"action": "reject"}
        )
        assert response.status_code == 422

    def test_invalid_action_returns_422(self, db, test_user, second_user, client_as_admin):
        game = Game(
            id="game-report-1",
            name="Reported Game",
            description="desc",
            game_type="Card",
            min_players=2,
            max_players=6,
            duration="30-45 minutes",
            objective="win",
            setup="setup",
            rules="rules",
            is_public=True,
            status="approved",
            contributor_id=test_user.id,
        )
        db.add(game)
        db.commit()
        report = _report_game(db, game.id, second_user.id)

        response = client_as_admin.patch(
            f"/admin/games/reports/{report.id}", json={"action": "banana"}
        )
        assert response.status_code == 422

    def test_dismiss_leaves_game_untouched(self, db, test_user, second_user, client_as_admin, client_no_auth):
        game = Game(
            id="game-dismiss-1",
            name="Fine Game",
            description="desc",
            game_type="Card",
            min_players=2,
            max_players=6,
            duration="30-45 minutes",
            objective="win",
            setup="setup",
            rules="rules",
            is_public=True,
            status="approved",
            contributor_id=test_user.id,
        )
        db.add(game)
        db.commit()
        report = _report_game(db, game.id, second_user.id)

        response = client_as_admin.patch(
            f"/admin/games/reports/{report.id}", json={"action": "dismiss"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "dismissed"

        db.refresh(game)
        assert game.status == "approved"
        listed = client_no_auth.get("/games/").json()
        assert game.id in {g["id"] for g in listed}

    def test_reject_report_hides_game_and_sets_reason(self, db, test_user, second_user, client_as_admin, client_no_auth):
        game = Game(
            id="game-actioned-1",
            name="Bad Game",
            description="desc",
            game_type="Card",
            min_players=2,
            max_players=6,
            duration="30-45 minutes",
            objective="win",
            setup="setup",
            rules="rules",
            is_public=True,
            status="approved",
            contributor_id=test_user.id,
        )
        db.add(game)
        db.commit()
        report = _report_game(db, game.id, second_user.id, reason="Spam")

        response = client_as_admin.patch(
            f"/admin/games/reports/{report.id}",
            json={"action": "reject", "rejection_reason_code": "Spam"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "actioned"

        db.refresh(game)
        assert game.status == "rejected"
        assert game.rejection_reason_code == "Spam"
        assert game.rejection_reason == "Reported: Spam"
        listed = client_no_auth.get("/games/").json()
        assert game.id not in {g["id"] for g in listed}
