import uuid

from src.db.tables import Game
from tests.api.games.helper import create_public_game


def _seed_game_owned_by(db, contributor_id: str, has_adult_content: bool = False) -> Game:
    game = Game(
        id=str(uuid.uuid4()),
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
        contributor_id=contributor_id,
        has_adult_content=has_adult_content,
    )
    db.add(game)
    db.commit()
    return game


class TestSetGameAdultContent:
    def test_requires_admin(self, client_with_auth, db):
        game = create_public_game(client_with_auth, db)
        response = client_with_auth.patch(
            f"/games/{game['id']}/adult-content", json={"has_adult_content": True}
        )
        assert response.status_code == 403

    def test_requires_auth(self, client_no_auth):
        response = client_no_auth.patch(
            "/games/some-id/adult-content", json={"has_adult_content": True}
        )
        assert response.status_code == 401

    def test_missing_game_is_404(self, client_as_admin):
        response = client_as_admin.patch(
            "/games/does-not-exist/adult-content", json={"has_adult_content": True}
        )
        assert response.status_code == 404

    def test_flags_game_as_adult_content(self, client_as_admin, db, test_user):
        # Only ONE client fixture per test — see note in test_games_verify.py.
        game = _seed_game_owned_by(db, test_user.id, has_adult_content=False)
        response = client_as_admin.patch(
            f"/games/{game.id}/adult-content", json={"has_adult_content": True}
        )
        assert response.status_code == 200
        assert response.json()["has_adult_content"] is True

        db.refresh(game)
        assert game.has_adult_content is True

    def test_unflags_game_as_adult_content(self, client_as_admin, db, test_user):
        game = _seed_game_owned_by(db, test_user.id, has_adult_content=True)
        response = client_as_admin.patch(
            f"/games/{game.id}/adult-content", json={"has_adult_content": False}
        )
        assert response.status_code == 200
        assert response.json()["has_adult_content"] is False
