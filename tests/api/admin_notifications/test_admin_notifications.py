from unittest.mock import patch

from src.db.tables import Notification, User


class TestSendToUser:
    def test_requires_admin(self, client_with_auth, test_user):
        response = client_with_auth.post(
            "/admin/notifications",
            json={"target": "user", "user_id": test_user.id, "title": "Hi", "body": "There"},
        )
        assert response.status_code == 403

    def test_requires_auth(self, client_no_auth):
        response = client_no_auth.post(
            "/admin/notifications",
            json={"target": "user", "user_id": "x", "title": "Hi", "body": "There"},
        )
        assert response.status_code == 401

    def test_missing_user_id_for_user_target_is_422(self, client_as_admin):
        response = client_as_admin.post(
            "/admin/notifications", json={"target": "user", "title": "Hi", "body": "There"}
        )
        assert response.status_code == 422

    def test_unknown_user_id_is_404(self, client_as_admin):
        response = client_as_admin.post(
            "/admin/notifications",
            json={"target": "user", "user_id": "does-not-exist", "title": "Hi", "body": "There"},
        )
        assert response.status_code == 404

    def test_sends_synchronously_and_logs_notification_with_game_id(self, client_as_admin, db, test_user):
        response = client_as_admin.post(
            "/admin/notifications",
            json={"target": "user", "user_id": test_user.id, "game_id": "g1", "title": "Hi", "body": "There"},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "sent"}

        note = db.query(Notification).filter_by(user_id=test_user.id).first()
        assert note.status == "no_token"  # test_user has no push token registered
        assert note.data == '{"game_id": "g1"}'


class TestBroadcast:
    def test_requires_admin(self, client_with_auth):
        response = client_with_auth.post(
            "/admin/notifications", json={"target": "broadcast", "title": "Hi", "body": "There"}
        )
        assert response.status_code == 403

    def test_dispatches_via_background_task_and_reaches_active_users(
        self, client_as_admin, db, test_user, second_user
    ):
        # The background task opens its own SessionLocal() in production (separate lifecycle
        # from the request-scoped `db`). In tests we redirect it to the same per-test `db`
        # session so we can assert on real behavior, and neutralize db.close() so the task's
        # cleanup doesn't tear down the session the test still needs afterward.
        with patch("src.api.admin_notifications.SessionLocal", return_value=db), \
             patch.object(db, "close"):
            response = client_as_admin.post(
                "/admin/notifications",
                json={"target": "broadcast", "title": "Announcement", "body": "New feature!"},
            )
        assert response.status_code == 202
        assert response.json() == {"status": "queued"}

        notified_user_ids = {
            n.user_id for n in db.query(Notification).filter_by(title="Announcement").all()
        }
        assert test_user.id in notified_user_ids
        assert second_user.id in notified_user_ids

    def test_excludes_inactive_users(self, client_as_admin, db, test_user):
        inactive = User(
            id="inactive-user-id", firstname="I", lastname="U", username="inactiveuser",
            email="inactive@example.com", hashed_password="x", is_active=False,
        )
        db.add(inactive)
        db.commit()

        with patch("src.api.admin_notifications.SessionLocal", return_value=db), \
             patch.object(db, "close"):
            client_as_admin.post(
                "/admin/notifications",
                json={"target": "broadcast", "title": "Announcement2", "body": "New feature!"},
            )

        notified_user_ids = {
            n.user_id for n in db.query(Notification).filter_by(title="Announcement2").all()
        }
        assert "inactive-user-id" not in notified_user_ids
