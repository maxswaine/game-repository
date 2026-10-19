from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.tables import (
    User, Game, UserFavourites, UserAchievement,
    GameReport, GameAlias, GameComment, CommentLike,
)
from src.utils.config import DELETED_USER_ID

PURGE_AFTER_DAYS = 30


def run_purge(db: Session) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=PURGE_AFTER_DAYS)

    candidates = db.query(User).filter(
        User.is_active == False,
        User.deletion_requested_at.isnot(None),
    ).all()

    purged = 0
    for user in candidates:
        deletion_time = user.deletion_requested_at
        if deletion_time.tzinfo is None:
            deletion_time = deletion_time.replace(tzinfo=timezone.utc)
        if deletion_time >= cutoff:
            continue
        _purge_user(db, user)
        purged += 1

    return purged


def _purge_user(db: Session, user: User) -> None:
    user_id = str(user.id)

    # The author chose at deletion time whether their games outlive the account
    # (DELETE /users/me?keep_games=...). NULL means they were never asked, which
    # keeps the original behaviour: private games go with the account.
    if user.keep_games_on_delete:
        # A private game owned by the placeholder would be dormant — nobody can
        # sign in as it, and get_game_by_id hides non-public games from everyone
        # but the contributor and admins. Publishing them through the review
        # gate is what actually keeps the content usable.
        db.query(Game).filter(
            Game.contributor_id == user_id,
            Game.is_public == False,
        ).update({"is_public": True, "status": "pending"}, synchronize_session=False)

    private_game_ids = [
        g.id for g in db.query(Game).filter(
            Game.contributor_id == user_id,
            Game.is_public == False,
        ).all()
    ]

    if private_game_ids:
        comment_ids = [
            c.id for c in db.query(GameComment).filter(
                GameComment.game_id.in_(private_game_ids)
            ).all()
        ]
        if comment_ids:
            db.query(CommentLike).filter(
                CommentLike.comment_id.in_(comment_ids)
            ).delete(synchronize_session=False)
        db.query(GameComment).filter(
            GameComment.game_id.in_(private_game_ids)
        ).delete(synchronize_session=False)
        db.query(GameAlias).filter(
            GameAlias.game_id.in_(private_game_ids)
        ).delete(synchronize_session=False)
        db.query(UserFavourites).filter(
            UserFavourites.game_id.in_(private_game_ids)
        ).delete(synchronize_session=False)
        db.query(Game).filter(
            Game.id.in_(private_game_ids)
        ).delete(synchronize_session=False)

    # Whatever survived the block above is public by now, so this reassigns all
    # of it without needing to re-check is_public.
    db.query(Game).filter(
        Game.contributor_id == user_id,
    ).update({"contributor_id": DELETED_USER_ID}, synchronize_session=False)

    # Likes outlive the account, reassigned to the placeholder the same way
    # public games, comments and approved aliases are. UserFavourites is keyed
    # (game_id, user_id), so the placeholder cannot hold two rows for one game:
    # where it already has one, drop the duplicate. Game.upvotes is untouched
    # either way, so the game's displayed total never changes.
    already_held = select(UserFavourites.game_id).where(
        UserFavourites.user_id == DELETED_USER_ID
    )
    db.query(UserFavourites).filter(
        UserFavourites.user_id == user_id,
        UserFavourites.game_id.in_(already_held),
    ).delete(synchronize_session=False)
    db.query(UserFavourites).filter(
        UserFavourites.user_id == user_id
    ).update({"user_id": DELETED_USER_ID}, synchronize_session=False)
    db.query(UserAchievement).filter(
        UserAchievement.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(GameReport).filter(
        GameReport.reporter_id == user_id
    ).delete(synchronize_session=False)

    db.query(GameComment).filter(
        GameComment.user_id == user_id
    ).update({"user_id": DELETED_USER_ID}, synchronize_session=False)

    db.query(GameAlias).filter(
        GameAlias.suggested_by == user_id,
        GameAlias.status == "approved",
    ).update({"suggested_by": DELETED_USER_ID}, synchronize_session=False)
    db.query(GameAlias).filter(
        GameAlias.suggested_by == user_id,
        GameAlias.status != "approved",
    ).delete(synchronize_session=False)

    db.delete(user)
    db.commit()
