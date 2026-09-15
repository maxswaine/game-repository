import uuid
from datetime import datetime, timezone

from src.db.tables import Notification


def _make_notification(db, user_id, **overrides):
    note = Notification(
        id=str(uuid.uuid4()),
        user_id=user_id,
        type="custom",
        title="Hi",
        body="There",
        status="sent",
        **overrides,
    )
    db.add(note)
    db.commit()
    return note


class TestMarkNotificationOpened:
    def test_requires_auth(self, client_no_auth, db, test_user):
        note = _make_notification(db, test_user.id)
        response = client_no_auth.post(f"/notifications/{note.id}/opened")
        assert response.status_code == 401

    def test_marks_opened_at(self, client_with_auth, db, test_user):
        note = _make_notification(db, test_user.id)
        assert note.opened_at is None

        response = client_with_auth.post(f"/notifications/{note.id}/opened")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        db.refresh(note)
        assert note.opened_at is not None

    def test_second_call_does_not_overwrite_first_open(self, client_with_auth, db, test_user):
        note = _make_notification(db, test_user.id)
        first_open = datetime(2026, 1, 1, tzinfo=timezone.utc)
        note.opened_at = first_open
        db.commit()

        response = client_with_auth.post(f"/notifications/{note.id}/opened")

        assert response.status_code == 200
        db.refresh(note)
        assert note.opened_at == first_open.replace(tzinfo=None)

    def test_unknown_id_is_404(self, client_with_auth):
        response = client_with_auth.post("/notifications/does-not-exist/opened")
        assert response.status_code == 404

    def test_other_users_notification_is_404(self, client_as_second_user, db, test_user):
        note = _make_notification(db, test_user.id)
        response = client_as_second_user.post(f"/notifications/{note.id}/opened")
        assert response.status_code == 404
        db.refresh(note)
        assert note.opened_at is None
