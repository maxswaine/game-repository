import uuid
from datetime import datetime, timezone

from src.db.tables import User


def test_delete_account_returns_200_with_message(client_with_auth, test_user):
    response = client_with_auth.delete(f"/users/{test_user.id}")
    assert response.status_code == 200
    assert response.json()["message"] == "Account successfully deleted"


def test_delete_account_forbidden_for_different_user(client_with_auth):
    other_id = str(uuid.uuid4())
    response = client_with_auth.delete(f"/users/{other_id}")
    assert response.status_code == 403
