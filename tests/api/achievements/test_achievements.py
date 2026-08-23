import uuid
from itertools import count
from unittest.mock import patch

import pytest

from src.db.tables import Game, UserAchievement
from src.models.enums.achievement_enum import AchievementTypeEnum
from tests.api.games.helper import create_public_game
from tests.utils import valid_public_game_payload

_vector_counter = count()


def _unique_embedding(_text):
    """Each call gets a distinct one-hot vector, so games in a loop never
    collide with each other on the duplicate-detection cosine-similarity
    check (see src/api/games.py) regardless of how similar their text is."""
    idx = next(_vector_counter) % 1536
    vector = [0.0] * 1536
    vector[idx] = 1.0
    return vector


@pytest.fixture(autouse=True)
def mock_embeddings():
    with patch("src.api.games.embed_text", side_effect=_unique_embedding):
        yield


def _get_achievements(client):
    return client.get("/achievements/").json()


def _by_type(achievements, achievement_type: AchievementTypeEnum):
    return next(a for a in achievements if a["achievement_type"] == achievement_type.value)


class TestGetAchievements:
    def test_requires_auth(self, client_no_auth):
        assert client_no_auth.get("/achievements/").status_code == 401

    def test_returns_all_eight_locked_for_new_user(self, client_with_auth, db):
        achievements = _get_achievements(client_with_auth)
        assert len(achievements) == 8
        assert all(not a["achieved"] for a in achievements)
        assert all(a["achieved_at"] is None for a in achievements)

    def test_returns_all_expected_types(self, client_with_auth, db):
        types = {a["achievement_type"] for a in _get_achievements(client_with_auth)}
        assert types == {t.value for t in AchievementTypeEnum}


class TestFirstLike:
    def test_unlocked_by_upvoting_a_game(self, client_with_auth, db):
        game = create_public_game(client_with_auth, db)
        client_with_auth.post(f"/games/{game['id']}/upvote")

        first_like = _by_type(_get_achievements(client_with_auth), AchievementTypeEnum.FIRST_LIKE)
        assert first_like["achieved"] is True
        assert first_like["achieved_at"] is not None

    def test_unlocked_by_favouriting_a_game(self, client_with_auth, db):
        game = create_public_game(client_with_auth, db)
        client_with_auth.post(f"/favourites/{game['id']}")

        first_like = _by_type(_get_achievements(client_with_auth), AchievementTypeEnum.FIRST_LIKE)
        assert first_like["achieved"] is True

    def test_not_granted_again_when_upvote_removed(self, client_with_auth, db):
        game = create_public_game(client_with_auth, db)
        client_with_auth.post(f"/games/{game['id']}/upvote")  # add
        client_with_auth.post(f"/games/{game['id']}/upvote")  # remove (toggle)

        first_like = _by_type(_get_achievements(client_with_auth), AchievementTypeEnum.FIRST_LIKE)
        assert first_like["achieved"] is True  # still achieved even after toggle off


class TestFirstSubmit:
    def test_unlocked_after_creating_first_game(self, client_with_auth, db):
        create_public_game(client_with_auth, db)

        first_submit = _by_type(_get_achievements(client_with_auth), AchievementTypeEnum.FIRST_SUBMIT)
        assert first_submit["achieved"] is True

    def test_not_unlocked_before_any_game(self, client_with_auth):
        first_submit = _by_type(_get_achievements(client_with_auth), AchievementTypeEnum.FIRST_SUBMIT)
        assert first_submit["achieved"] is False


class TestFiveUploads:
    def test_not_unlocked_after_four_games(self, client_with_auth):
        for i in range(4):
            client_with_auth.post("/games/", json=valid_public_game_payload({"name": f"Game {i}"}))

        five_uploads = _by_type(_get_achievements(client_with_auth), AchievementTypeEnum.FIVE_UPLOADS)
        assert five_uploads["achieved"] is False

    def test_unlocked_after_fifth_game(self, client_with_auth):
        for i in range(5):
            client_with_auth.post("/games/", json=valid_public_game_payload({"name": f"Game {i}"}))

        five_uploads = _by_type(_get_achievements(client_with_auth), AchievementTypeEnum.FIVE_UPLOADS)
        assert five_uploads["achieved"] is True


class TestTenLikes:
    def test_unlocked_for_contributor_when_game_hits_10_upvotes(
        self, db, test_user, client_as_second_user
    ):
        game = Game(
            id=str(uuid.uuid4()),
            name="Popular Game",
            description="A great game",
            game_type="Card",
            min_players=2,
            max_players=6,
            duration="30-45 minutes",
            objective="Win",
            setup="Set up",
            rules="Follow rules",
            is_public=True,
            upvotes=9,
            contributor_id=test_user.id,
        )
        db.add(game)
        db.commit()

        response = client_as_second_user.post(f"/games/{game.id}/upvote")
        assert response.status_code == 200

        achievement = db.query(UserAchievement).filter_by(
            user_id=test_user.id,
            achievement_type=AchievementTypeEnum.TEN_LIKES_ON_UPLOAD.value,
        ).first()
        assert achievement is not None

    def test_not_unlocked_at_nine_upvotes(self, db, test_user, client_as_second_user):
        game = Game(
            id=str(uuid.uuid4()),
            name="Almost Popular",
            description="A great game",
            game_type="Card",
            min_players=2,
            max_players=6,
            duration="30-45 minutes",
            objective="Win",
            setup="Set up",
            rules="Follow rules",
            is_public=True,
            upvotes=8,
            contributor_id=test_user.id,
        )
        db.add(game)
        db.commit()

        client_as_second_user.post(f"/games/{game.id}/upvote")

        achievement = db.query(UserAchievement).filter_by(
            user_id=test_user.id,
            achievement_type=AchievementTypeEnum.TEN_LIKES_ON_UPLOAD.value,
        ).first()
        assert achievement is None


class TestSignalAchievements:
    @pytest.mark.parametrize("achievement_type", [
        AchievementTypeEnum.SHARE_GAME,
        AchievementTypeEnum.GIVE_FEEDBACK,
        AchievementTypeEnum.COMPLETE_TUTORIAL,
    ])
    def test_signal_grants_achievement(self, client_with_auth, achievement_type):
        response = client_with_auth.post(
            "/achievements/signal",
            json={"achievement_type": achievement_type.value},
        )
        assert response.status_code == 201

        achievement = _by_type(_get_achievements(client_with_auth), achievement_type)
        assert achievement["achieved"] is True
        assert achievement["achieved_at"] is not None

    def test_signal_is_idempotent(self, client_with_auth):
        client_with_auth.post("/achievements/signal", json={"achievement_type": "share_game"})
        response = client_with_auth.post("/achievements/signal", json={"achievement_type": "share_game"})
        assert response.status_code == 201

    def test_signal_rejects_data_derived_achievement(self, client_with_auth):
        response = client_with_auth.post(
            "/achievements/signal",
            json={"achievement_type": AchievementTypeEnum.FIRST_LIKE.value},
        )
        assert response.status_code == 400

    def test_signal_requires_auth(self, client_no_auth):
        response = client_no_auth.post(
            "/achievements/signal",
            json={"achievement_type": "share_game"},
        )
        assert response.status_code == 401


class TestFeedbackGrantsAchievement:
    def test_submitting_feedback_grants_give_feedback_achievement(self, client_with_auth):
        response = client_with_auth.post(
            "/feedback", json={"type": "Bug Report", "message": "Something broke"}
        )
        assert response.status_code == 201

        achievement = _by_type(_get_achievements(client_with_auth), AchievementTypeEnum.GIVE_FEEDBACK)
        assert achievement["achieved"] is True
        assert achievement["achieved_at"] is not None

    def test_second_feedback_submission_does_not_error(self, client_with_auth):
        client_with_auth.post("/feedback", json={"type": "Bug Report", "message": "First"})
        response = client_with_auth.post("/feedback", json={"type": "Other", "message": "Second"})
        assert response.status_code == 201

        achievements = _get_achievements(client_with_auth)
        assert len([a for a in achievements if a["achievement_type"] == "give_feedback" and a["achieved"]]) == 1


class TestScenarios:
    def test_five_game_journey_unlocks_first_submit_and_five_uploads(self, client_with_auth):
        """Creating 5 games should unlock FIRST_SUBMIT on game 1 and FIVE_UPLOADS on game 5."""
        for i in range(5):
            client_with_auth.post("/games/", json=valid_public_game_payload({"name": f"Game {i}"}))

        achievements = _get_achievements(client_with_auth)
        assert _by_type(achievements, AchievementTypeEnum.FIRST_SUBMIT)["achieved"] is True
        assert _by_type(achievements, AchievementTypeEnum.FIVE_UPLOADS)["achieved"] is True

    def test_pre_seeded_games_count_toward_five_uploads(self, db, test_user, client_with_auth):
        """4 games seeded directly in DB, 5th submitted via API — five_uploads should unlock."""
        for i in range(4):
            db.add(Game(
                id=str(uuid.uuid4()),
                name=f"Seeded Game {i}",
                description="desc",
                game_type="Card",
                min_players=2,
                max_players=6,
                duration="30-45 minutes",
                objective="win",
                setup="setup",
                rules="rules",
                is_public=True,
                contributor_id=test_user.id,
            ))
        db.commit()

        create_public_game(client_with_auth, db)

        five_uploads = _by_type(_get_achievements(client_with_auth), AchievementTypeEnum.FIVE_UPLOADS)
        assert five_uploads["achieved"] is True

    def test_achievements_isolated_between_users(self, db, second_user, client_with_auth):
        """User A's game submissions don't unlock achievements for user B."""
        for _ in range(5):
            create_public_game(client_with_auth, db)

        second_user_achievements = db.query(UserAchievement).filter_by(
            user_id=second_user.id
        ).all()
        assert len(second_user_achievements) == 0

    def test_five_uploads_achievement_survives_game_deletion(self, client_with_auth, db):
        """Deleting a game after hitting 5 uploads must not revoke the achievement."""
        game_ids = []
        for i in range(5):
            game = create_public_game(client_with_auth, db)
            game_ids.append(game["id"])

        five_uploads = _by_type(_get_achievements(client_with_auth), AchievementTypeEnum.FIVE_UPLOADS)
        assert five_uploads["achieved"] is True

        client_with_auth.delete(f"/games/{game_ids[0]}")

        five_uploads_after = _by_type(_get_achievements(client_with_auth), AchievementTypeEnum.FIVE_UPLOADS)
        assert five_uploads_after["achieved"] is True
        assert five_uploads_after["achieved_at"] == five_uploads["achieved_at"]

    def test_ten_likes_not_double_granted_when_upvote_toggled_past_10(
        self, db, test_user, client_as_second_user
    ):
        """Game hits 10 → down to 9 → back to 10. Achievement granted only once."""
        game = Game(
            id=str(uuid.uuid4()),
            name="Toggleable Game",
            description="desc",
            game_type="Card",
            min_players=2,
            max_players=6,
            duration="30-45 minutes",
            objective="win",
            setup="setup",
            rules="rules",
            is_public=True,
            upvotes=9,
            contributor_id=test_user.id,
        )
        db.add(game)
        db.commit()

        client_as_second_user.post(f"/games/{game.id}/upvote")  # → 10, achievement granted
        client_as_second_user.post(f"/games/{game.id}/upvote")  # → 9
        client_as_second_user.post(f"/games/{game.id}/upvote")  # → 10 again

        count = db.query(UserAchievement).filter_by(
            user_id=test_user.id,
            achievement_type=AchievementTypeEnum.TEN_LIKES_ON_UPLOAD.value,
        ).count()
        assert count == 1


class TestFavouriteUpvoteSync:
    def test_favouriting_increments_upvotes(self, client_with_auth, db):
        game = create_public_game(client_with_auth, db)
        assert game["upvotes"] == 0

        client_with_auth.post(f"/favourites/{game['id']}")

        updated = client_with_auth.get(f"/games/{game['id']}").json()
        assert updated["upvotes"] == 1

    def test_unfavouriting_decrements_upvotes(self, client_with_auth, db):
        game = create_public_game(client_with_auth, db)
        client_with_auth.post(f"/favourites/{game['id']}")
        client_with_auth.delete(f"/favourites/{game['id']}")

        updated = client_with_auth.get(f"/games/{game['id']}").json()
        assert updated["upvotes"] == 0
