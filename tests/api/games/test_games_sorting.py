import uuid
from datetime import datetime, timezone, timedelta

from src.db.tables import Game, UserFavourites
from src.models.enums.sort_by_enum import SortByEnum
from tests.utils import valid_public_game_payload


def _make_game(db, test_user, *, name, upvotes=0, verified=False, created_at=None):
    game = Game(
        id=str(uuid.uuid4()),
        name=name,
        description="desc",
        age_rating="7+",
        game_type="Card",
        min_players=2,
        max_players=6,
        duration="30-45 minutes",
        objective="win",
        setup="setup",
        rules="rules",
        is_public=True,
        upvotes=upvotes,
        is_whats_that_game_verified=verified,
        contributor_id=test_user.id,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(game)
    return game


def _make_like(db, game_id, user_id, *, created_at):
    db.add(UserFavourites(game_id=game_id, user_id=user_id, created_at=created_at))


class TestSortRecent:
    def test_sort_recent_returns_newest_first(self, db, test_user, client_no_auth):
        old = _make_game(db, test_user, name="Old Game",
                         created_at=datetime.now(timezone.utc) - timedelta(days=10))
        new = _make_game(db, test_user, name="New Game",
                         created_at=datetime.now(timezone.utc) - timedelta(days=1))
        db.commit()

        response = client_no_auth.get("/games/?sort_by=recent")
        assert response.status_code == 200
        names = [g["name"] for g in response.json()]
        assert names.index("New Game") < names.index("Old Game")

    def test_sort_by_none_defaults_to_recent_order(self, db, test_user, client_no_auth):
        _make_game(db, test_user, name="First Created",
                   created_at=datetime.now(timezone.utc) - timedelta(days=5))
        _make_game(db, test_user, name="Last Created",
                   created_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        db.commit()

        response = client_no_auth.get("/games/")
        assert response.status_code == 200
        names = [g["name"] for g in response.json()]
        assert names.index("Last Created") < names.index("First Created")

    def test_sort_by_invalid_value_returns_422(self, client_no_auth):
        response = client_no_auth.get("/games/?sort_by=bogus")
        assert response.status_code == 422


class TestSortTrending:
    def test_sort_trending_uses_window(self, db, test_user, second_user, client_no_auth):
        game_a = _make_game(db, test_user, name="Hot This Week")
        game_b = _make_game(db, test_user, name="Old Favourite")
        db.commit()

        now = datetime.now(timezone.utc)
        _make_like(db, game_a.id, test_user.id, created_at=now - timedelta(days=1))
        _make_like(db, game_a.id, second_user.id, created_at=now - timedelta(days=2))
        for i in range(5):
            fav_user_id = str(uuid.uuid4())
            # Insert users first (FK constraint)
            from src.db.tables import User
            db.add(User(
                id=fav_user_id, firstname="u", lastname="u",
                username=f"u{i}{uuid.uuid4().hex[:4]}", email=f"u{i}{uuid.uuid4().hex[:4]}@x.com",
                is_active=True, created_at=now, last_updated=now,
            ))
            db.flush()
            _make_like(db, game_b.id, fav_user_id, created_at=now - timedelta(days=30))
        db.commit()

        response = client_no_auth.get("/games/?sort_by=trending&trending_days=7")
        assert response.status_code == 200
        names = [g["name"] for g in response.json()]
        assert names.index("Hot This Week") < names.index("Old Favourite")

    def test_sort_trending_respects_window_param(self, db, test_user, second_user, client_no_auth):
        game_a = _make_game(db, test_user, name="Recent Two")
        game_b = _make_game(db, test_user, name="Old Five")
        db.commit()

        now = datetime.now(timezone.utc)
        _make_like(db, game_a.id, test_user.id, created_at=now - timedelta(days=1))
        _make_like(db, game_a.id, second_user.id, created_at=now - timedelta(days=2))

        from src.db.tables import User
        for i in range(5):
            uid = str(uuid.uuid4())
            db.add(User(
                id=uid, firstname="u", lastname="u",
                username=f"w{i}{uuid.uuid4().hex[:4]}", email=f"w{i}{uuid.uuid4().hex[:4]}@x.com",
                is_active=True, created_at=now, last_updated=now,
            ))
            db.flush()
            _make_like(db, game_b.id, uid, created_at=now - timedelta(days=45))
        db.commit()

        response = client_no_auth.get("/games/?sort_by=trending&trending_days=60")
        assert response.status_code == 200
        names = [g["name"] for g in response.json()]
        assert names.index("Old Five") < names.index("Recent Two")

    def test_sort_trending_games_with_no_recent_likes_still_appear(
        self, db, test_user, client_no_auth
    ):
        _make_game(db, test_user, name="No Likes Game")
        db.commit()

        response = client_no_auth.get("/games/?sort_by=trending&trending_days=7")
        assert response.status_code == 200
        names = [g["name"] for g in response.json()]
        assert "No Likes Game" in names

    def test_trending_days_clamped_below(self, db, test_user, client_no_auth):
        _make_game(db, test_user, name="Any Game")
        db.commit()
        response = client_no_auth.get("/games/?sort_by=trending&trending_days=0")
        assert response.status_code == 200

    def test_trending_days_clamped_above(self, db, test_user, client_no_auth):
        _make_game(db, test_user, name="Any Game")
        db.commit()
        response = client_no_auth.get("/games/?sort_by=trending&trending_days=9999")
        assert response.status_code == 200


class TestSortRecommended:
    def test_verified_game_ranks_above_unverified(self, db, test_user, client_no_auth):
        _make_game(db, test_user, name="Unverified Popular", upvotes=100, verified=False)
        _make_game(db, test_user, name="WTG Verified", upvotes=1, verified=True)
        db.commit()

        response = client_no_auth.get("/games/?sort_by=recommended")
        assert response.status_code == 200
        names = [g["name"] for g in response.json()]
        assert names.index("WTG Verified") < names.index("Unverified Popular")

    def test_tiebreak_by_upvotes_when_neither_verified(self, db, test_user, client_no_auth):
        _make_game(db, test_user, name="Low Votes", upvotes=2)
        _make_game(db, test_user, name="High Votes", upvotes=50)
        db.commit()

        response = client_no_auth.get("/games/?sort_by=recommended")
        assert response.status_code == 200
        names = [g["name"] for g in response.json()]
        assert names.index("High Votes") < names.index("Low Votes")


class TestSortCombinedWithFilters:
    def test_sort_trending_applies_within_filtered_subset(
        self, db, test_user, second_user, client_no_auth
    ):
        card_game = _make_game(db, test_user, name="Card Hot")
        _make_game(db, test_user, name="Board Cold")
        card_game.game_type = "Card"
        db.flush()
        db.commit()

        now = datetime.now(timezone.utc)
        _make_like(db, card_game.id, test_user.id, created_at=now - timedelta(days=1))
        db.commit()

        response = client_no_auth.get("/games/?sort_by=trending&game_type=Card")
        assert response.status_code == 200
        data = response.json()
        assert all(g["game_type"] == "Card" for g in data)
        assert any(g["name"] == "Card Hot" for g in data)
