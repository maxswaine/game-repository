import uuid
from datetime import datetime, timezone, timedelta

from src.db.tables import User, Game, GameComment, GameAlias, UserFavourites, UserAchievement
from src.services.purge import run_purge
from src.utils.config import DELETED_USER_ID


def _make_user_past_window(db) -> User:
    user = User(
        id=str(uuid.uuid4()),
        firstname="Purge",
        lastname="Me",
        username=f"purge_{uuid.uuid4().hex[:8]}",
        email=f"purge_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=None,
        is_active=False,
        deletion_requested_at=datetime.now(timezone.utc) - timedelta(days=31),
        created_at=datetime.now(timezone.utc),
        last_updated=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_purge_removes_user_past_window(db):
    user = _make_user_past_window(db)
    user_id = user.id

    run_purge(db)

    assert db.query(User).filter(User.id == user_id).first() is None


def test_purge_reassigns_public_game_to_placeholder(db):
    user = _make_user_past_window(db)
    game = Game(
        id=str(uuid.uuid4()),
        name="Public Game",
        description="desc",
        game_type="card",
        min_players=2,
        max_players=4,
        duration="30-45 min",
        objective="win",
        setup="setup",
        rules="rules",
        contributor_id=user.id,
        is_public=True,
    )
    db.add(game)
    db.commit()

    run_purge(db)

    db.expire(game)
    game = db.query(Game).filter(Game.id == game.id).first()
    assert game is not None
    assert game.contributor_id == DELETED_USER_ID


def test_purge_deletes_private_game(db):
    user = _make_user_past_window(db)
    game = Game(
        id=str(uuid.uuid4()),
        name="Private Game",
        description="desc",
        game_type="card",
        min_players=2,
        max_players=4,
        duration="30-45 min",
        objective="win",
        setup="setup",
        rules="rules",
        contributor_id=user.id,
        is_public=False,
    )
    db.add(game)
    db.commit()
    game_id = game.id

    run_purge(db)

    assert db.query(Game).filter(Game.id == game_id).first() is None


def test_purge_anonymises_comments(db):
    placeholder_user = db.query(User).filter(User.id == DELETED_USER_ID).first()
    user = _make_user_past_window(db)
    public_game = Game(
        id=str(uuid.uuid4()),
        name="Commented Game",
        description="desc",
        game_type="card",
        min_players=2,
        max_players=4,
        duration="30-45 min",
        objective="win",
        setup="setup",
        rules="rules",
        contributor_id=placeholder_user.id,
        is_public=True,
    )
    db.add(public_game)
    comment = GameComment(
        id=str(uuid.uuid4()),
        game_id=public_game.id,
        user_id=user.id,
        body="Great game!",
        comment_type="general",
    )
    db.add(comment)
    db.commit()
    comment_id = comment.id

    run_purge(db)

    db.expire_all()
    comment = db.query(GameComment).filter(GameComment.id == comment_id).first()
    assert comment is not None
    assert comment.user_id == DELETED_USER_ID


def test_purge_skips_user_inside_window(db):
    user = User(
        id=str(uuid.uuid4()),
        firstname="Keep",
        lastname="Me",
        username=f"keep_{uuid.uuid4().hex[:8]}",
        email=f"keep_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=None,
        is_active=False,
        deletion_requested_at=datetime.now(timezone.utc) - timedelta(days=5),
        created_at=datetime.now(timezone.utc),
        last_updated=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    user_id = user.id

    run_purge(db)

    assert db.query(User).filter(User.id == user_id).first() is not None


def _public_game(db, contributor_id, upvotes=0) -> Game:
    game = Game(
        id=str(uuid.uuid4()),
        name="Liked Game",
        description="desc",
        game_type="card",
        min_players=2,
        max_players=4,
        duration="30-45 min",
        objective="win",
        setup="setup",
        rules="rules",
        contributor_id=contributor_id,
        is_public=True,
        upvotes=upvotes,
    )
    db.add(game)
    db.commit()
    return game


def test_purge_reassigns_likes_to_placeholder(db):
    """A like survives the account that placed it, like games and comments do."""
    owner = _make_user_past_window(db)
    liker = _make_user_past_window(db)
    game = _public_game(db, DELETED_USER_ID, upvotes=1)
    db.add(UserFavourites(game_id=game.id, user_id=liker.id))
    db.commit()

    run_purge(db)

    rows = db.query(UserFavourites).filter(UserFavourites.game_id == game.id).all()
    assert [r.user_id for r in rows] == [DELETED_USER_ID]
    db.expire(game)
    assert db.query(Game).filter(Game.id == game.id).first().upvotes == 1


def test_purge_drops_a_like_the_placeholder_already_holds(db):
    """(game_id, user_id) is the PK, so the placeholder cannot hold two rows
    for one game. The duplicate goes; Game.upvotes keeps the real total."""
    liker = _make_user_past_window(db)
    game = _public_game(db, DELETED_USER_ID, upvotes=2)
    db.add(UserFavourites(game_id=game.id, user_id=DELETED_USER_ID))
    db.add(UserFavourites(game_id=game.id, user_id=liker.id))
    db.commit()

    run_purge(db)

    rows = db.query(UserFavourites).filter(UserFavourites.game_id == game.id).all()
    assert [r.user_id for r in rows] == [DELETED_USER_ID]
    db.expire(game)
    assert db.query(Game).filter(Game.id == game.id).first().upvotes == 2


def test_purge_still_drops_likes_on_deleted_private_games(db):
    """Private games are deleted outright, so their likes cannot be kept."""
    user = _make_user_past_window(db)
    private_game = Game(
        id=str(uuid.uuid4()),
        name="Private Game",
        description="desc",
        game_type="card",
        min_players=2,
        max_players=4,
        duration="30-45 min",
        objective="win",
        setup="setup",
        rules="rules",
        contributor_id=user.id,
        is_public=False,
    )
    db.add(private_game)
    db.commit()
    game_id = private_game.id
    db.add(UserFavourites(game_id=game_id, user_id=user.id))
    db.commit()

    run_purge(db)

    assert db.query(Game).filter(Game.id == game_id).first() is None
    assert db.query(UserFavourites).filter(UserFavourites.game_id == game_id).count() == 0
