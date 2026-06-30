import uuid
from datetime import datetime, timezone

from starlette.testclient import TestClient

from src.api.users import get_current_user_optional
from src.db.database import get_db
from src.db.tables import Game, GameEquipment, User
from src.main import app
from tests.api.games.helper import create_public_game, create_private_game, get_user_token
from tests.conftest import client_with_auth, client_no_auth


def test_get_games_returns_list(client_with_auth, client_no_auth):
    created_game = create_public_game(client_with_auth)

    get_response = client_no_auth.get("/games/")
    assert get_response.status_code == 200

    data = get_response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    game = data[0]
    assert game["name"] == created_game["name"]
    assert game["game_type"] == created_game["game_type"]
    assert game["player_count"]["min_players"] == created_game["player_count"]["min_players"]
    assert game["player_count"]["max_players"] == created_game["player_count"]["max_players"]

    assert len(game["equipment"]) == len(created_game["equipment"])
    assert set(game["equipment"]) == set(created_game["equipment"])

    assert set(game["game_setting"]) == set(created_game["game_setting"])

    assert game["contributor"]["username"] == created_game["contributor"]["username"]
    assert game["contributor"]["country_of_origin"] == created_game["contributor"]["country_of_origin"]


def test_get_private_game_valid(client_with_auth, db, test_user):
    created_game = create_private_game(client_with_auth)
    game_id = created_game["id"]

    user_login = {"username": "testuser", "password": "password"}
    token = get_user_token(client_with_auth, user_login)
    headers = {"Authorization": f"Bearer {token}"}

    get_response = client_with_auth.get(f"/games/{game_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json() is not None


def test_get_games_does_not_crash_for_oauth_contributor(db, client_no_auth):
    oauth_user = User(
        id=str(uuid.uuid4()),
        firstname="OAuth",
        lastname="User",
        username="oauthcontributor",
        email="oauth@gmail.com",
        hashed_password="",
        country_of_origin=None,
        is_active=True,
        oauth_provider="google",
        oauth_id="google-sub-999",
        created_at=datetime.now(timezone.utc),
    )
    db.add(oauth_user)
    db.flush()

    game = Game(
        id=str(uuid.uuid4()),
        name="OAuth Game",
        description="A game contributed by an OAuth user with no country set",
        game_type="Card",
        min_players=2,
        max_players=6,
        duration="30-45 mins",
        objective="Win",
        setup="Setup the game",
        rules="Play by the rules",
        is_public=True,
        is_whats_that_game_verified=False,
        upvotes=0,
        contributor_id=oauth_user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(game)
    db.flush()
    db.add(GameEquipment(game_id=game.id, equipment_name="No Equipment"))
    db.commit()

    response = client_no_auth.get("/games/")
    assert response.status_code == 200


def test_get_private_game_forbidden(client_with_auth, db, second_user):
    created_game = create_private_game(client_with_auth)
    game_id = created_game["id"]

    app.dependency_overrides.clear()

    def override_get_db():
        yield db

    def override_get_current_user_optional():
        return second_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional

    with TestClient(app) as client_as_second_user:
        resp = client_as_second_user.get(f"/games/{game_id}")
        assert resp.status_code == 403

    app.dependency_overrides.clear()
