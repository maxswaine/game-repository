# src/api/favourites.py
from typing import List, Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from src.api.games import map_game_to_read
from src.api.users import get_current_active_user
from src.db.database import get_db
from src.db.tables import User, Game, UserFavourites
from src.models import GameRead
from src.models.enums.achievement_enum import AchievementTypeEnum
from src.models.user_models.user import UserFavouriteBase
from src.services.achievements import grant_if_not_exists

router = APIRouter()


def auth_required():
    return Depends(get_current_active_user)


@router.get("/", response_model=List[GameRead], status_code=200)
def get_all_favourites(
        db: Annotated[Session, Depends(get_db)],
        current_user: User = auth_required(),
        limit: int = 20,
        offset: int = 0,
):
    limit = min(limit, 100)
    offset = max(offset, 0)

    favourite_game_ids = (
        db.query(UserFavourites.game_id)
        .filter(UserFavourites.user_id == current_user.id)
        .limit(limit)
        .offset(offset)
        .all()
    )

    game_ids = [fav.game_id for fav in favourite_game_ids]

    if not game_ids:
        return []

    games = (
        db.query(Game)
        .filter(Game.id.in_(game_ids))
        .options(
            joinedload(Game.equipment_items),
            joinedload(Game.setting_items),
            joinedload(Game.contributor)
        )
        .all()
    )

    return [map_game_to_read(game, set(game_ids)) for game in games]


@router.post("/{game_id}", response_model=UserFavouriteBase, status_code=201,
             responses={404: {"description": "Game not found"},
                        400: {"description": "Game is already favourited by this user"}})
def add_favourite(
        db: Annotated[Session, Depends(get_db)],
        game_id: str,
        current_user: User = auth_required()
):
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    existing = db.query(UserFavourites).filter(
        UserFavourites.user_id == current_user.id,
        UserFavourites.game_id == game_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Game is already favourited by this user")

    is_first_like = db.query(UserFavourites).filter(
        UserFavourites.user_id == current_user.id
    ).count() == 0

    db_favourite_relationship = UserFavourites(
        game_id=game_id,
        user_id=current_user.id
    )
    db.add(db_favourite_relationship)
    game.upvotes += 1

    if is_first_like:
        grant_if_not_exists(db, current_user.id, AchievementTypeEnum.FIRST_LIKE)

    db.commit()
    db.refresh(db_favourite_relationship)
    return db_favourite_relationship


@router.delete("/{game_id}", status_code=204, responses={404: {"description": "Favourite not found"}})
def remove_favourite(
        db: Annotated[Session, Depends(get_db)],
        game_id: str,
        current_user: User = auth_required()
):
    existing = db.query(UserFavourites).filter(
        UserFavourites.user_id == current_user.id,
        UserFavourites.game_id == game_id
    ).first()

    if not existing:
        raise HTTPException(status_code=404, detail="Favourite not found")

    game = db.query(Game).filter(Game.id == existing.game_id).first()
    db.delete(existing)
    if game:
        game.upvotes = max(0, game.upvotes - 1)
    db.commit()