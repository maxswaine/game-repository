import pytest

from tests.conftest import client_with_auth, client_no_auth


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
