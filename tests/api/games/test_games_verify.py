import uuid

from src.db.tables import Game, UserAchievement
from src.models.enums.achievement_enum import AchievementTypeEnum
from tests.api.games.helper import create_public_game


def _seed_game_owned_by(db, contributor_id: str) -> Game:
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
    )
    db.add(game)
    db.commit()
    return game


class TestVerifyGame:
    def test_requires_admin(self, client_with_auth):
        game = create_public_game(client_with_auth)
        response = client_with_auth.post(f"/games/{game['id']}/verify")
        assert response.status_code == 403

    def test_requires_auth(self, client_no_auth):
        response = client_no_auth.post("/games/some-id/verify")
        assert response.status_code == 401

    def test_missing_game_is_404(self, client_as_admin):
        response = client_as_admin.post("/games/does-not-exist/verify")
        assert response.status_code == 404

    def test_sets_verified_flag(self, client_as_admin, db, test_user):
        # Only ONE client fixture per test — app.dependency_overrides is one dict on one app
        # object, so mixing client_with_auth + client_as_admin in the same test makes the
        # later fixture's auth override win for the whole test body, silently collapsing both
        # "clients" onto admin_user. Seed the game directly in the DB instead of creating it
        # via a second client.
        game = _seed_game_owned_by(db, test_user.id)
        response = client_as_admin.post(f"/games/{game.id}/verify")
        assert response.status_code == 200
        assert response.json()["is_whats_that_game_certified"] is True

    def test_grants_hall_of_fame_to_contributor(self, client_as_admin, db, test_user):
        game = _seed_game_owned_by(db, test_user.id)
        client_as_admin.post(f"/games/{game.id}/verify")

        achievement = db.query(UserAchievement).filter_by(
            user_id=test_user.id,
            achievement_type=AchievementTypeEnum.HALL_OF_FAME.value,
        ).first()
        assert achievement is not None

    def test_idempotent_on_repeat_verify(self, client_as_admin, db, test_user):
        game = _seed_game_owned_by(db, test_user.id)
        client_as_admin.post(f"/games/{game.id}/verify")
        client_as_admin.post(f"/games/{game.id}/verify")

        count = db.query(UserAchievement).filter_by(
            user_id=test_user.id,
            achievement_type=AchievementTypeEnum.HALL_OF_FAME.value,
        ).count()
        assert count == 1
