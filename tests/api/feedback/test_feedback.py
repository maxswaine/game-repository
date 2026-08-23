import pytest

from tests.conftest import client_with_auth, client_no_auth, client_as_admin


def _post_feedback(client, feedback_type="Bug Report", message="Something broke"):
    return client.post(
        "/feedback",
        json={"type": feedback_type, "message": message},
    )


def test_create_feedback_returns_201(client_with_auth):
    response = _post_feedback(client_with_auth)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert "created_at" in data


def test_create_feedback_all_valid_types(client_with_auth):
    for t in ["Bug Report", "Feature Request", "General Feedback", "Other"]:
        response = _post_feedback(client_with_auth, feedback_type=t)
        assert response.status_code == 201, f"Failed for type: {t}"


def test_create_feedback_unauthenticated_returns_401(client_no_auth):
    response = _post_feedback(client_no_auth)
    assert response.status_code == 401


def test_create_feedback_empty_message_returns_422(client_with_auth):
    response = _post_feedback(client_with_auth, message="")
    assert response.status_code == 422


def test_create_feedback_message_too_long_returns_422(client_with_auth):
    response = _post_feedback(client_with_auth, message="x" * 2001)
    assert response.status_code == 422


def test_create_feedback_invalid_type_returns_422(client_with_auth):
    response = _post_feedback(client_with_auth, feedback_type="Not A Real Type")
    assert response.status_code == 422


def test_non_admin_cannot_list_feedback(client_with_auth):
    _post_feedback(client_with_auth)
    response = client_with_auth.get("/admin/feedback")
    assert response.status_code == 403


def test_unauthenticated_cannot_list_feedback(client_no_auth):
    response = client_no_auth.get("/admin/feedback")
    assert response.status_code == 401


def test_admin_can_list_feedback(client_with_auth, client_as_admin):
    _post_feedback(client_with_auth, feedback_type="Bug Report", message="First")
    _post_feedback(client_with_auth, feedback_type="Other", message="Second")

    response = client_as_admin.get("/admin/feedback")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert {item["message"] for item in data} == {"First", "Second"}
    assert all("user_id" in item and "status" in item for item in data)


def test_admin_list_feedback_includes_username(db, test_user, client_as_admin):
    from src.db.tables import Feedback

    db.add(Feedback(user_id=test_user.id, type="Bug Report", message="Needs a username"))
    db.commit()

    response = client_as_admin.get("/admin/feedback")
    assert response.status_code == 200
    data = response.json()
    item = next(i for i in data if i["message"] == "Needs a username")
    assert item["user_id"] == test_user.id
    assert item["username"] == test_user.username


def test_new_feedback_defaults_to_pending(client_with_auth, client_as_admin):
    _post_feedback(client_with_auth, message="Fresh feedback")
    data = client_as_admin.get("/admin/feedback").json()
    item = next(i for i in data if i["message"] == "Fresh feedback")
    assert item["status"] == "pending"


class TestResolveFeedback:
    def _create(self, db, test_user, message="Needs review"):
        from src.db.tables import Feedback

        feedback = Feedback(user_id=test_user.id, type="Bug Report", message=message)
        db.add(feedback)
        db.commit()
        db.refresh(feedback)
        return feedback

    def test_acknowledge_sets_status(self, db, test_user, client_as_admin):
        feedback = self._create(db, test_user)
        response = client_as_admin.patch(
            f"/admin/feedback/{feedback.id}", json={"action": "acknowledge"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "acknowledged"

    def test_needs_work_sets_status(self, db, test_user, client_as_admin):
        feedback = self._create(db, test_user)
        response = client_as_admin.patch(
            f"/admin/feedback/{feedback.id}", json={"action": "needs_work"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "needs_work"

    def test_invalid_action_returns_422(self, db, test_user, client_as_admin):
        feedback = self._create(db, test_user)
        response = client_as_admin.patch(
            f"/admin/feedback/{feedback.id}", json={"action": "banana"}
        )
        assert response.status_code == 422

    def test_missing_feedback_returns_404(self, client_as_admin):
        response = client_as_admin.patch(
            "/admin/feedback/does-not-exist", json={"action": "acknowledge"}
        )
        assert response.status_code == 404

    def test_non_admin_cannot_resolve(self, db, test_user, client_with_auth):
        feedback = self._create(db, test_user)
        response = client_with_auth.patch(
            f"/admin/feedback/{feedback.id}", json={"action": "acknowledge"}
        )
        assert response.status_code == 403

    def test_unauthenticated_cannot_resolve(self, db, test_user, client_no_auth):
        feedback = self._create(db, test_user)
        response = client_no_auth.patch(
            f"/admin/feedback/{feedback.id}", json={"action": "acknowledge"}
        )
        assert response.status_code == 401

    def test_resolved_feedback_drops_out_of_pending_list(self, db, test_user, client_as_admin):
        feedback = self._create(db, test_user, message="Will be acknowledged")
        client_as_admin.patch(f"/admin/feedback/{feedback.id}", json={"action": "acknowledge"})

        data = client_as_admin.get("/admin/feedback").json()
        assert not any(i["id"] == feedback.id for i in data)
