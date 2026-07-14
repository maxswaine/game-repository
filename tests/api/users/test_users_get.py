import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.api.users import get_current_active_user
from src.db.database import get_db
from src.db.tables import User
from src.main import app


def test_get_me_returns_200_for_oauth_user_before_complete_profile(db):
    user = User(
        id=str(uuid.uuid4()),
        firstname="OAuth",
        lastname="User",
        username="oauthuser123",
        email="oauth@example.com",
        hashed_password=None,
        country_of_origin=None,
        date_of_birth=None,
        oauth_provider="google",
        oauth_id="google-oauth-id",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    def override_get_db():
        yield db

    def override_get_current_active_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user

    try:
        with TestClient(app) as client:
            response = client.get("/users/me")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "oauthuser123"
    assert data["country_of_origin"] is None
    assert data["date_of_birth"] is None
