from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload

from backend.api.users import get_current_active_user
from backend.core.exceptions import FORBIDDEN_EXCEPTION
from backend.db.database import get_db
from backend.db.tables import Game, GameEquipment, GameTheme, User
from backend.models.enums import GameType, AgeRating, Vote
from backend.models.game import GameCreate, GameRead, GameUpdate
from backend.models.game_equipment import GameEquipmentBase
from backend.models.game_theme import GameThemeBase
from backend.models.player_count import PlayerCount
from backend.models.user import UserPublicRead

router = APIRouter()


# CREATE
@router.post("/", response_model=GameRead, status_code=201)
def create_new_game(new_game: GameCreate, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_active_user)):
    if not current_user:
        return FORBIDDEN_EXCEPTION

    db_new_game = Game(
        name=new_game.name,
        description=new_game.description,
        age_rating=new_game.age_rating,
        game_type=new_game.game_type,
        min_players=new_game.player_count.min_players,
        max_players=new_game.player_count.max_players,
        duration=new_game.duration,
        rules=new_game.rules,
        image_url=new_game.image_url,
        is_public=new_game.is_public,
        created_at=datetime.now(timezone.utc),
        contributor_id=current_user.id
    )
    db.add(db_new_game)
    db.commit()
    db.refresh(db_new_game)

    for eq in new_game.equipment:
        db.add(GameEquipment(game_id=db_new_game.id, equipment_name=eq.equipment_name))

    for th in new_game.themes:
        db.add(GameTheme(game_id=db_new_game.id, theme_name=th.theme_name))

    db.commit()
    db.refresh(db_new_game)

    return map_game_to_read(db_new_game)

@router.post("/{game_id}/upvote", status_code=200)
def upvote_game(
        game_id: str,
        remove: bool,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
):
    return change_game_votes(Vote.upvote, game_id, current_user, db)


@router.post("/{game_id}/downvote", status_code=200)
def downvote_game(
        game_id: str,
        remove: bool,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
):
    return change_game_votes(Vote.downvote, game_id, remove, current_user, db)


def change_game_votes(vote_change: Vote, game_id: str, remove: bool,
                      current_user: User,
                      db: Session):
    if not current_user:
        raise FORBIDDEN_EXCEPTION

    db_game: Game = db.query(Game).filter(Game.id == game_id).first()
    if not db_game:
        raise HTTPException(status_code=404, detail="Game not found")

    if vote_change == Vote.upvote and not remove:
        db_game.upvotes += 1
    elif vote_change == Vote.upvote and remove:
        db_game.upvotes -= 1
    elif vote_change == Vote.downvote and not remove:
        db_game.downvotes += 1
    elif vote_change == Vote.downvote and remove:
        db_game.upvotes -= 1

    db.commit()
    db.refresh(db_game)
    return {"upvotes": db_game.upvotes, "downvotes": db_game.downvotes}


# READ
@router.get("/", response_model=List[GameRead])
def get_all_games(
        name: Optional[str] = None,
        game_type: Optional[GameType] = None,
        age_rating: Optional[AgeRating] = None,
        min_players: Optional[int] = None,
        max_players: Optional[int] = None,
        duration: Optional[str] = None,
        theme: Optional[str] = None,
        equipment: Optional[str] = None,
        db: Session = Depends(get_db),
):

    query = db.query(Game).options(
        joinedload(Game.equipment_items),  # eager-load equipment
        joinedload(Game.theme_items),  # eager-load themes
        joinedload(Game.contributor)  # eager-load contributor
    ).filter(Game.is_public == True)

    if name:
        query = query.filter(Game.name.ilike(f"%{name}%"))

    if game_type:
        query = query.filter(Game.game_type == game_type)

    if age_rating:
        query = query.filter(Game.age_rating == age_rating)

    if min_players:
        query = query.filter(Game.min_players >= min_players)

    if max_players:
        query = query.filter(Game.max_players <= max_players)

    if duration:
        query = query.filter(Game.duration.ilike(f"%{duration}%"))

    if theme:
        query = query.join(Game.theme_items).filter(GameTheme.theme_name.ilike(f"%{theme}%"))

    if equipment:
        query = query.join(Game.equipment_items).filter(GameEquipment.equipment_name.ilike(f"%{equipment}%"))

    games = query.distinct().all()

    # Map ORM objects to GameRead Pydantic model
    return [map_game_to_read(game) for game in games]


# UPDATE
@router.patch("/{game_id}", response_model=GameRead, status_code=status.HTTP_200_OK)
def update_game(
        game_id: str,
        updates: GameUpdate,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db),
):
    if not current_user:
        return FORBIDDEN_EXCEPTION

    db_game = db.query(Game).filter(Game.id == game_id).first()
    if not db_game:
        raise HTTPException(status_code=404, detail="Game not found")

    update_data = updates.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key in ["equipment", "themes"]:
            continue
        setattr(db_game, key, value)

    db.commit()
    db.refresh(db_game)

    return map_game_to_read(db_game)


def map_game_to_read(db_game: Game) -> GameRead:
    return GameRead(
        id=db_game.id,
        name=db_game.name,
        description=db_game.description,
        age_rating=db_game.age_rating,
        game_type=db_game.game_type,
        player_count=PlayerCount(
            min_players=db_game.min_players,
            max_players=db_game.max_players
        ),
        duration=db_game.duration,
        equipment=[GameEquipmentBase(equipment_name=eq.equipment_name) for eq in db_game.equipment_items],
        themes=[GameThemeBase(theme_name=th.theme_name) for th in db_game.theme_items],
        rules=db_game.rules,
        image_url=db_game.image_url,
        is_public=db_game.is_public,
        upvotes=db_game.upvotes,
        downvotes=db_game.downvotes,
        contributor=UserPublicRead(
            username=db_game.contributor.username,
            country_of_origin=db_game.contributor.country_of_origin,
        ),
        created_at=db_game.created_at
    )


# DELETE
@router.delete("/{game_id}", status_code=204)
def delete_game(game_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    if not current_user:
        return FORBIDDEN_EXCEPTION
    db_game = db.query(Game).filter(Game.id == game_id).first()
    if not db_game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Authorization check: only the contributor can delete
    if db_game.contributor_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not allowed to delete this game")

    db.delete(db_game)
    db.commit()
    return None
# Methods
