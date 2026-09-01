import pytest
from starlette.testclient import TestClient

from src.api.users import get_current_active_user
from src.db.database import get_db
from src.db.tables import Notification
from src.main import app
from tests.api.games.helper import create_public_game
from tests.conftest import client_with_auth, client_no_auth, client_as_second_user


def _create_comment(client, game_id, body="Great game!", comment_type="general"):
    return client.post(
        f"/games/{game_id}/comments",
        json={"body": body, "comment_type": comment_type},
    )


def test_create_comment_returns_201(client_with_auth, db):
    game = create_public_game(client_with_auth, db)
    response = _create_comment(client_with_auth, game["id"])
    assert response.status_code == 201
    data = response.json()
    assert data["body"] == "Great game!"
    assert data["comment_type"] == "general"
    assert data["likes"] == 0
    assert data["liked_by_me"] is False
    assert data["user"]["username"] == "testuser"


def test_create_comment_notifies_contributor(client_as_second_user, db, test_user):
    # Only ONE client fixture per test — mixing client_with_auth + client_as_second_user
    # collapses both onto the later fixture's auth override. Seed the game directly
    # owned by test_user instead of creating it via a second client (see test_games_verify.py).
    import uuid as _uuid
    from src.db.tables import Game

    game = Game(
        id=str(_uuid.uuid4()),
        name="Contributor's Game",
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

    response = _create_comment(client_as_second_user, game.id, body="Nice one!")
    assert response.status_code == 201

    note = db.query(Notification).filter_by(user_id=test_user.id, type="new_comment").first()
    assert note is not None
    assert note.title == "New comment"
    assert game.name in note.body
    assert "Nice one!" in note.body


def test_create_comment_rule_variant_notifies_with_variant_copy(client_as_second_user, db, test_user):
    import uuid as _uuid
    from src.db.tables import Game

    game = Game(
        id=str(_uuid.uuid4()),
        name="Contributor's Game",
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

    response = _create_comment(client_as_second_user, game.id, comment_type="rule_variant")
    assert response.status_code == 201

    note = db.query(Notification).filter_by(user_id=test_user.id, type="new_comment").first()
    assert note is not None
    assert note.title == "New rule variant"
    assert "added a rule variant to" in note.body
    assert game.name in note.body


def test_create_comment_on_own_game_does_not_notify_self(client_with_auth, db, test_user):
    game = create_public_game(client_with_auth, db)
    response = _create_comment(client_with_auth, game["id"])
    assert response.status_code == 201

    note = db.query(Notification).filter_by(user_id=test_user.id, type="new_comment").first()
    assert note is None


def test_create_comment_rule_variant_type(client_with_auth, db):
    game = create_public_game(client_with_auth, db)
    response = _create_comment(client_with_auth, game["id"], comment_type="rule_variant")
    assert response.status_code == 201
    assert response.json()["comment_type"] == "rule_variant"


def test_create_comment_body_too_long_returns_422(client_with_auth, db):
    game = create_public_game(client_with_auth, db)
    response = _create_comment(client_with_auth, game["id"], body="x" * 1001)
    assert response.status_code == 422


def test_create_comment_profanity_returns_422(client_with_auth, db):
    game = create_public_game(client_with_auth, db)
    response = _create_comment(client_with_auth, game["id"], body="this game is fucking shit")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "content_policy_violation"


def test_create_comment_rule_variant_profanity_returns_422(client_with_auth, db):
    game = create_public_game(client_with_auth, db)
    response = _create_comment(
        client_with_auth, game["id"], body="rule: everyone is a bitch", comment_type="rule_variant"
    )
    assert response.status_code == 422


def test_create_comment_unauthenticated_returns_401(client_no_auth, db):
    response = client_no_auth.post(
        "/games/any-id/comments",
        json={"body": "Hi"},
    )
    assert response.status_code == 401


def test_get_comments_returns_list(client_with_auth, client_no_auth, db):
    game = create_public_game(client_with_auth, db)
    _create_comment(client_with_auth, game["id"], "First")
    _create_comment(client_with_auth, game["id"], "Second")

    response = client_no_auth.get(f"/games/{game['id']}/comments")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_comments_sorted_by_likes(client_with_auth, client_as_second_user, db):
    game = create_public_game(client_with_auth, db)
    c1 = _create_comment(client_with_auth, game["id"], "Less liked").json()
    c2 = _create_comment(client_with_auth, game["id"], "More liked").json()

    # Like c2 from two users
    client_with_auth.post(f"/games/{game['id']}/comments/{c2['id']}/like")
    client_as_second_user.post(f"/games/{game['id']}/comments/{c2['id']}/like")

    response = client_with_auth.get(f"/games/{game['id']}/comments")
    comments = response.json()
    assert comments[0]["id"] == c2["id"]


def test_like_comment_increments_likes(client_with_auth, db):
    game = create_public_game(client_with_auth, db)
    comment = _create_comment(client_with_auth, game["id"]).json()

    response = client_with_auth.post(
        f"/games/{game['id']}/comments/{comment['id']}/like"
    )
    assert response.status_code == 200
    assert response.json()["likes"] == 1
    assert response.json()["liked_by_me"] is True


def test_like_comment_toggle_removes_like(client_with_auth, db):
    game = create_public_game(client_with_auth, db)
    comment = _create_comment(client_with_auth, game["id"]).json()

    client_with_auth.post(f"/games/{game['id']}/comments/{comment['id']}/like")
    response = client_with_auth.post(
        f"/games/{game['id']}/comments/{comment['id']}/like"
    )
    assert response.json()["likes"] == 0
    assert response.json()["liked_by_me"] is False


def test_liked_by_me_false_for_unauthenticated(client_with_auth, client_no_auth, db):
    game = create_public_game(client_with_auth, db)
    comment = _create_comment(client_with_auth, game["id"]).json()
    client_with_auth.post(f"/games/{game['id']}/comments/{comment['id']}/like")

    response = client_no_auth.get(f"/games/{game['id']}/comments")
    assert response.json()[0]["liked_by_me"] is False


def test_delete_own_comment_returns_204(client_with_auth, db):
    game = create_public_game(client_with_auth, db)
    comment = _create_comment(client_with_auth, game["id"]).json()

    response = client_with_auth.delete(
        f"/games/{game['id']}/comments/{comment['id']}"
    )
    assert response.status_code == 204


def test_delete_other_users_comment_returns_403(client_with_auth, db, second_user):
    game = create_public_game(client_with_auth, db)
    comment = _create_comment(client_with_auth, game["id"]).json()

    app.dependency_overrides.clear()

    def override_get_db():
        yield db

    def override_get_current_active_user():
        return second_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user

    with TestClient(app) as second_client:
        response = second_client.delete(
            f"/games/{game['id']}/comments/{comment['id']}"
        )
        assert response.status_code == 403

    app.dependency_overrides.clear()


def test_get_comments_unknown_game_returns_404(client_no_auth):
    response = client_no_auth.get("/games/nonexistent-id/comments")
    assert response.status_code == 404
