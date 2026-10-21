from unittest.mock import MagicMock, patch

from src.db.tables import Notification, PushDeliveryTicket, PushToken, User


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


def _echoing_expo_client():
    """An Expo client that accepts every message and returns one pending ticket each."""
    def publish_multiple(messages):
        tickets = []
        for message in messages:
            ticket = MagicMock()
            ticket.id = f"ticket-{message.to}"
            ticket.push_message.to = message.to
            ticket.validate_response.return_value = None
            tickets.append(ticket)
        return tickets

    client = MagicMock()
    client.publish_multiple.side_effect = publish_multiple
    return client


class TestBroadcastAudience:
    def test_default_audience_leaves_anonymous_devices_alone(self, client_as_admin, db, test_user):
        # Back-compat: an admin client that predates `audience` must reach exactly who it did
        # before, so a signed-out device must NOT start receiving its broadcasts implicitly.
        db.add(PushToken(token="ExponentPushToken[anon]", user_id=None, device_id="d1", platform="ios"))
        db.commit()

        with patch("src.api.admin_notifications.SessionLocal", return_value=db), \
             patch.object(db, "close"), \
             patch("src.services.notifications._get_push_client") as mock_get_client:
            client_as_admin.post(
                "/admin/notifications",
                json={"target": "broadcast", "title": "UsersOnly", "body": "Hi"},
            )

        # test_user has no token, so no user send reaches Expo either — the point is that the
        # anonymous device was never enumerated.
        mock_get_client.assert_not_called()
        notes = db.query(Notification).filter_by(title="UsersOnly").all()
        assert notes
        assert all(n.user_id is not None for n in notes)

    def test_audience_devices_reaches_anonymous_tokens_and_no_users(
        self, client_as_admin, db, test_user, second_user
    ):
        db.add(PushToken(token="ExponentPushToken[anon]", user_id=None, device_id="d1", platform="ios"))
        db.add(PushToken(token="ExponentPushToken[user]", user_id=test_user.id, platform="ios"))
        db.commit()

        with patch("src.api.admin_notifications.SessionLocal", return_value=db), \
             patch.object(db, "close"), \
             patch("src.services.notifications._get_push_client", return_value=_echoing_expo_client()):
            response = client_as_admin.post(
                "/admin/notifications",
                json={"target": "broadcast", "title": "DevicesOnly", "body": "Hi", "audience": "devices"},
            )
        assert response.status_code == 202

        notes = db.query(Notification).filter_by(title="DevicesOnly").all()
        assert len(notes) == 1
        assert notes[0].user_id is None
        assert notes[0].status == "sent"

        # The signed-in user's token must not be in the device sweep.
        tickets = db.query(PushDeliveryTicket).filter_by(notification_id=notes[0].id).all()
        assert [t.token for t in tickets] == ["ExponentPushToken[anon]"]

    def test_audience_all_reaches_each_token_exactly_once(self, client_as_admin, db, test_user):
        db.add(PushToken(token="ExponentPushToken[anon]", user_id=None, device_id="d1", platform="ios"))
        db.add(PushToken(
            token="ExponentPushToken[user]", user_id=test_user.id, device_id="d2", platform="ios",
        ))
        db.commit()

        with patch("src.api.admin_notifications.SessionLocal", return_value=db), \
             patch.object(db, "close"), \
             patch("src.services.notifications._get_push_client", return_value=_echoing_expo_client()):
            response = client_as_admin.post(
                "/admin/notifications",
                json={"target": "broadcast", "title": "Everyone", "body": "Hi", "audience": "all"},
            )
        assert response.status_code == 202

        # The two sweeps filter on `user_id = <id>` and `user_id IS NULL`, which are mutually
        # exclusive, so no device may be published to twice by one broadcast. Delivery tickets
        # are the proof: one row per (notification, token) actually handed to Expo.
        note_ids = [n.id for n in db.query(Notification).filter_by(title="Everyone").all()]
        tokens_pushed = [
            t.token for t in db.query(PushDeliveryTicket).filter(
                PushDeliveryTicket.notification_id.in_(note_ids)
            ).all()
        ]
        assert sorted(tokens_pushed) == ["ExponentPushToken[anon]", "ExponentPushToken[user]"]
