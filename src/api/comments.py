from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from src.api.users import get_current_active_user, get_current_user_optional
from src.core.exceptions import GAME_NOT_FOUND_EXCEPTION, FORBIDDEN_EXCEPTION
from src.db.database import get_db
from src.db.tables import Game, GameComment, CommentLike
from src.models.comment_models.comment import CommentCreate, CommentRead
from src.models.enums.role_enum import Role
from src.services.moderation import check_content
from src.utils.age_filter import detect_profanity

router = APIRouter()


def _load_comment(db: Session, comment_id: str) -> GameComment:
    return (
        db.query(GameComment)
        .options(joinedload(GameComment.user), joinedload(GameComment.like_records))
        .filter(GameComment.id == comment_id)
        .first()
    )


def _map_comment(comment: GameComment, current_user_id: Optional[str]) -> CommentRead:
    liked_by_me = (
        any(like.user_id == current_user_id for like in comment.like_records)
        if current_user_id
        else False
    )
    return CommentRead(
        id=comment.id,
        game_id=comment.game_id,
        user=comment.user,
        body=comment.body,
        comment_type=comment.comment_type,
        likes=comment.likes,
        liked_by_me=liked_by_me,
        created_at=comment.created_at,
    )


@router.get("/{game_id}/comments", response_model=list[CommentRead])
def get_comments(
    game_id: str,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_optional),
):
    if not db.query(Game).filter(Game.id == game_id).first():
        raise GAME_NOT_FOUND_EXCEPTION
    comments = (
        db.query(GameComment)
        .options(joinedload(GameComment.user), joinedload(GameComment.like_records))
        .filter(GameComment.game_id == game_id)
        .order_by(GameComment.likes.desc(), GameComment.created_at.desc())
        .limit(min(limit, 100))
        .offset(max(offset, 0))
        .all()
    )
    current_user_id = current_user.id if current_user else None
    return [_map_comment(c, current_user_id) for c in comments]


@router.post("/{game_id}/comments", response_model=CommentRead, status_code=201)
def create_comment(
    game_id: str,
    body: CommentCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    if not db.query(Game).filter(Game.id == game_id).first():
        raise GAME_NOT_FOUND_EXCEPTION

    if detect_profanity(body.body) or not check_content(body.body):
        raise HTTPException(
            status_code=422,
            detail={"code": "content_policy_violation", "message": "Content violates community guidelines."},
        )

    comment = GameComment(
        game_id=game_id,
        user_id=current_user.id,
        body=body.body,
        comment_type=body.comment_type.value,
        created_at=datetime.now(timezone.utc),
    )
    db.add(comment)
    db.commit()
    return _map_comment(_load_comment(db, comment.id), current_user.id)


@router.delete("/{game_id}/comments/{comment_id}", status_code=204)
def delete_comment(
    game_id: str,
    comment_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    comment = db.query(GameComment).filter(
        GameComment.id == comment_id, GameComment.game_id == game_id
    ).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != current_user.id and current_user.role != Role.admin:
        raise FORBIDDEN_EXCEPTION
    db.delete(comment)
    db.commit()


@router.post("/{game_id}/comments/{comment_id}/like", response_model=CommentRead)
def toggle_like(
    game_id: str,
    comment_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    comment = db.query(GameComment).filter(
        GameComment.id == comment_id, GameComment.game_id == game_id
    ).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    existing = db.query(CommentLike).filter(
        CommentLike.comment_id == comment_id,
        CommentLike.user_id == current_user.id,
    ).first()

    if existing:
        db.delete(existing)
        comment.likes = max(0, comment.likes - 1)
    else:
        db.add(CommentLike(
            comment_id=comment_id,
            user_id=current_user.id,
            created_at=datetime.now(timezone.utc),
        ))
        comment.likes += 1

    db.commit()
    return _map_comment(_load_comment(db, comment_id), current_user.id)
