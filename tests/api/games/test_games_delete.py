from starlette.testclient import TestClient

from backend.api.users import get_current_active_user
from backend.db.database import get_db
from backend.main import app
from backend.models import GameRead
from tests.api.games.helper import create_public_game


def test_delete_game_success(client_with_auth):
    created_game: GameRead = create_public_game(client_with_auth)
    game_id = created_game["id"]
    resp = client_with_auth.delete(f"/games/{game_id}")
    assert resp.status_code == 204


def test_delete_game_unauthorized(client_with_auth, db):
    created_game = create_public_game(client_with_auth)
    game_id = created_game["id"]

    def override_get_db():
        yield db

    app.dependency_overrides = {get_db: override_get_db}

    with TestClient(app) as client_no_auth:
        resp = client_no_auth.delete(f"/games/{game_id}")
        assert resp.status_code == 401

    app.dependency_overrides.clear()


def test_delete_game_not_users(client_with_auth, db):
    created_game = create_public_game(client_with_auth)
    game_id = created_game["id"]

    def override_get_db():
        yield db

    app.dependency_overrides = {get_db: override_get_db}

    with TestClient(app) as client_no_auth:
        resp = client_no_auth.delete(f"/games/{game_id}")
        assert resp.status_code == 401

    app.dependency_overrides.clear()


def test_delete_game_not_owner(client_with_auth, db, second_user):
    created_game = create_public_game(client_with_auth)
    game_id = created_game["id"]

    app.dependency_overrides.clear()

    def override_get_db():
        yield db

    def override_get_current_active_user():
        return second_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user

    with TestClient(app) as client_as_second_user:
        resp = client_as_second_user.delete(f"/games/{game_id}")
        assert resp.status_code == 403

    # Optional: clear overrides after test
    app.dependency_overrides.clear()
