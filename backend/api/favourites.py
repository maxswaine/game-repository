from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from backend.api.games import map_game_to_read
from backend.api.users import get_current_active_user
from backend.db.database import get_db
from backend.db.tables import User, Game, UserFavourites
from backend.models import GameRead
from backend.models.user import UserFavouriteBase

router = APIRouter()


def auth_required():
    return Depends(get_current_active_user)


@router.get("/", response_model=List[GameRead], status_code=200)
def get_all_favourites(
        current_user: User = auth_required(),
        db: Session = Depends(get_db),
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
            joinedload(Game.theme_items),
            joinedload(Game.contributor)
        )
        .all()
    )

    return [map_game_to_read(game) for game in games]


@router.post("/{game_id}", response_model=UserFavouriteBase, status_code=201)
def add_favourite(game_id: str, current_user: User = auth_required(), db: Session = Depends(get_db)):
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    existing = db.query(UserFavourites).filter(
        UserFavourites.user_id == current_user.id,
        UserFavourites.game_id == game_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Game is already favourited by this user")

    db_favourite_relationship = UserFavourites(
        game_id=game_id,
        user_id=current_user.id
    )

    db.add(db_favourite_relationship)
    db.commit()
    db.refresh(db_favourite_relationship)
    return db_favourite_relationship


@router.delete("/{game_id}", status_code=204)
def remove_favourite(game_id: str, current_user: User = auth_required(), db: Session = Depends(get_db)):
    existing = db.query(UserFavourites).filter(
        UserFavourites.user_id == current_user.id,
        UserFavourites.game_id == game_id
    ).first()

    if not existing:
        raise HTTPException(status_code=404, detail="Favourite not found")

    db.delete(existing)
    db.commit()
