import uuid
from datetime import datetime, timezone

from src.db.tables import User, Game


def test_delete_account_deactivates_user(client_with_auth, test_user, db):
    response = client_with_auth.delete("/users/me")
    assert response.status_code == 200
    assert "30 days" in response.json()["message"]
    db.refresh(test_user)
    assert test_user.is_active is False
    assert test_user.deletion_requested_at is not None


def test_delete_account_with_game_returns_200_not_500(client_with_auth, test_user, db):
    game = Game(
        id=str(uuid.uuid4()),
        name="Test Game",
        description="A game",
        game_type="card",
        min_players=2,
        max_players=4,
        duration="30-45 min",
        objective="Win",
        setup="Setup steps",
        rules="The rules",
        contributor_id=test_user.id,
        is_public=True,
    )
    db.add(game)
    db.commit()

    response = client_with_auth.delete("/users/me")
    assert response.status_code == 200


def test_delete_account_unauthenticated_returns_401(client_no_auth):
    response = client_no_auth.delete("/users/me")
    assert response.status_code == 401
