from datetime import datetime, timezone

from src.db.tables import Game, GamePhoto, User


def _make_user(db):
    user = User(
        firstname="P", lastname="Q", username="photouser",
        email="photo@example.com", hashed_password="x",
        date_of_birth=datetime(1990, 1, 1), country_of_origin="GB",
    )
    db.add(user)
    db.flush()
    return user


def _make_game(db, user):
    game = Game(
        name="G", description="d", game_type="Card", min_players=1, max_players=4,
        duration="Short", objective="o", setup="s", rules="r",
        contributor_id=user.id, created_at=datetime.now(timezone.utc),
    )
    db.add(game)
    db.flush()
    return game


def test_photos_cascade_delete_with_game(db):
    user = _make_user(db)
    game = _make_game(db, user)
    db.add(GamePhoto(
        game_id=game.id, object_key="games/%s/a.jpg" % game.id,
        public_url="https://cdn.example.com/games/%s/a.jpg" % game.id, position=0,
    ))
    db.flush()

    assert db.query(GamePhoto).filter_by(game_id=game.id).count() == 1

    db.delete(game)
    db.flush()

    assert db.query(GamePhoto).filter_by(game_id=game.id).count() == 0
