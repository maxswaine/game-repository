from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List, Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload

from src.api.users import get_current_active_user, get_current_user_optional
from src.core.exceptions import GAME_NOT_FOUND_EXCEPTION, UNAUTHORIZED_EXCEPTION, FORBIDDEN_EXCEPTION
from src.db.database import get_db
from src.db.tables import Game, GameEquipment, GameSetting, User, UserFavourites
from src.models.enums.age_rating_enum import AgeRatingEnum
from src.models.enums.game_type_enum import GameTypeEnum
from src.models.error_models.error import ErrorDetail
from src.models.game_models.game import GameCreate, GameRead, GameUpdate
from src.models.game_models.game_report import GameReportRequest, GameReportResponse
from src.models.game_models.game_visibility import GameVisibility
from src.models.game_models.game_vote import GameVoteRead
from src.models.game_models.player_count import PlayerCount
from src.models.user_models.user import UserPublicRead

protected_router = APIRouter()
public_router = APIRouter()


def auth_required():
    return Depends(get_current_active_user)


# CREATE
@protected_router.post("/", response_model=GameRead, status_code=201, responses={422: {"model": ErrorDetail}})
def create_new_game(
        db: Annotated[Session, Depends(get_db)],
        new_game: GameCreate,
        current_user: User = auth_required()
):
    db_new_game = Game(
        name=new_game.name,
        description=new_game.description,
        age_rating=new_game.age_rating,
        game_type=new_game.game_type,
        min_players=new_game.player_count.min_players,
        max_players=new_game.player_count.max_players,
        duration=new_game.duration,
        objective=new_game.objective,
        setup=new_game.setup,
        rules=new_game.rules,
        image_url=new_game.image_url,
        is_public=new_game.is_public,
        is_whats_that_game_verified=new_game.is_whats_that_game_certified,
        created_at=datetime.now(timezone.utc),
        contributor_id=current_user.id
    )
    db.add(db_new_game)
    db.commit()
    db.refresh(db_new_game)

    for eq in new_game.equipment:
        db.add(GameEquipment(game_id=db_new_game.id, equipment_name=str(eq)))

    for s in (new_game.game_setting or []):
        db.add(GameSetting(game_id=db_new_game.id, setting_name=s))

    db.commit()
    db.refresh(db_new_game)

    return map_game_to_read(db_new_game)


@protected_router.post("/{game_id}/upvote", status_code=200, response_model=GameVoteRead,
                       responses={404: {"description": "Game not found"},
                                  401: {"description": "Authentication required"}})
def upvote_game(
        db: Annotated[Session, Depends(get_db)],
        game_id: str,
        current_user: User = auth_required()
):
    db_game: Game = db.query(Game).filter(Game.id == game_id).first()
    if not db_game:
        raise GAME_NOT_FOUND_EXCEPTION

    existing_favourite = db.query(UserFavourites).filter(
        UserFavourites.game_id == game_id,
        UserFavourites.user_id == current_user.id
    ).first()

    if existing_favourite:
        db.delete(existing_favourite)
        db_game.upvotes -= 1
    else:
        db.add(UserFavourites(game_id=game_id, user_id=current_user.id))
        db_game.upvotes += 1

    db.commit()
    db.refresh(db_game)

    return GameVoteRead(
        game_id=db_game.id,
        upvotes=db_game.upvotes,
    )


@protected_router.post("/{game_id}/report", status_code=201, response_model=GameReportResponse,
                       responses={404: {"description": "Game not found"},
                                  401: {"description": "Authentication required"}})
def report_game(
        db: Annotated[Session, Depends(get_db)],
        game_id: str,
        game_report: GameReportRequest,
        _current_user: User = auth_required()

):
    return GameReportResponse(message="Report received")


# READ
@public_router.get("/", response_model=List[GameRead], status_code=200,
                   responses={401: {"description": "Authentication required for non-public access"}})
def get_all_games(
        db: Annotated[Session, Depends(get_db)],
        name: Optional[str] = None,
        game_type: Optional[GameTypeEnum] = None,
        age_rating: Optional[AgeRatingEnum] = None,
        min_players: Optional[int] = None,
        max_players: Optional[int] = None,
        duration: Optional[str] = None,
        setting: Optional[str] = None,
        equipment: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
):
    limit = min(limit, 100)
    offset = max(offset, 0)
    query = db.query(Game).options(
        joinedload(Game.equipment_items),  # eager-load equipment
        joinedload(Game.setting_items),  # eager-load settings
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

    if setting:
        query = query.join(Game.setting_items).filter(GameSetting.setting_name.ilike(f"%{setting}%"))

    if equipment:
        query = query.join(Game.equipment_items).filter(GameEquipment.equipment_name.ilike(f"%{equipment}%"))

    games = (query.distinct()
             .limit(limit)
             .offset(offset)
             .all())

    return [map_game_to_read(game) for game in games]


@protected_router.get("/mine", response_model=List[GameRead], status_code=200,
                      responses={401: {"description": "Authentication required"}})
def get_my_games(
        db: Annotated[Session, Depends(get_db)],
        current_user: User = auth_required(),
        limit: int = 20,
        offset: int = 0,
):
    limit = min(limit, 100)
    offset = max(offset, 0)
    games = (db.query(Game).options(
        joinedload(Game.equipment_items),
        joinedload(Game.setting_items),
        joinedload(Game.contributor),
    ).filter(Game.contributor_id == current_user.id)
             .limit(limit)
             .offset(offset)
             .all())

    return [map_game_to_read(game) for game in games]


@public_router.get("/{game_id}", response_model=GameRead, status_code=200,
                   responses={404: {"description": "Game not found"}, 401: {"description": "Authentication required"}})
def get_game_by_id(
        db: Annotated[Session, Depends(get_db)],
        game_id: str,
        current_user: Annotated[User | None, Depends(get_current_user_optional)],
):
    game: Game | None = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    if not game.is_public:
        if not current_user or game.contributor_id != current_user.id:
            raise FORBIDDEN_EXCEPTION

    return map_game_to_read(game)


# UPDATE
@protected_router.patch("/{game_id}", response_model=GameRead, status_code=200,
                        responses={400: {"description": "Validation error"}, 404: {"description": "Game not found"},
                                   401: {"description": "Authentication required"}})
def update_game(
        db: Annotated[Session, Depends(get_db)],
        game_id: str,
        updates: GameUpdate,
        current_user: User = auth_required(),
):
    db_game = db.query(Game).filter(Game.id == game_id).first()
    if not db_game:
        raise GAME_NOT_FOUND_EXCEPTION

    if db_game.contributor_id != current_user.id:
        raise UNAUTHORIZED_EXCEPTION
    update_data = updates.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key in ["equipment", "game_setting"]:
            continue
        if value is None:
            continue
        setattr(db_game, key, value)

    if "equipment" in update_data:
        db.query(GameEquipment).filter(
            GameEquipment.game_id == db_game.id
        ).delete()

        for eq in updates.equipment or []:
            db.add(GameEquipment(
                game_id=db_game.id,
                equipment_name=eq
            ))

    if "game_setting" in update_data:
        db.query(GameSetting).filter(
            GameSetting.game_id == db_game.id
        ).delete()

        for s in updates.game_setting or []:
            db.add(GameSetting(
                game_id=db_game.id,
                setting_name=s
            ))

    db.commit()
    db.refresh(db_game)

    return map_game_to_read(db_game)


@protected_router.patch("/{game_id}/visibility", response_model=GameRead, status_code=200,
                        responses={400: {"description": "Validation error"}, 404: {"description": "Game not found"},
                                   401: {"description": "Authentication required"}})
def change_game_visibility(
        db: Annotated[Session, Depends(get_db)],
        game_id: str,
        game_visibility: GameVisibility,
        current_user: User = auth_required()
):
    db_game: Game = db.query(Game).filter(Game.id == game_id).first()
    if not db_game:
        raise GAME_NOT_FOUND_EXCEPTION
    if db_game.contributor_id != current_user.id:
        raise UNAUTHORIZED_EXCEPTION

    setattr(db_game, "is_public", game_visibility.is_public)

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
        equipment=[item.equipment_name for item in db_game.equipment_items],
        game_setting=[s.setting_name for s in db_game.setting_items],
        objective=db_game.objective,
        setup=db_game.setup,
        rules=db_game.rules,
        image_url=db_game.image_url,
        is_public=db_game.is_public,
        upvotes=db_game.upvotes,
        contributor=UserPublicRead(
            username=db_game.contributor.username,
            country_of_origin=db_game.contributor.country_of_origin,
        ),
        created_at=db_game.created_at,
        is_whats_that_game_certified=db_game.is_whats_that_game_verified
    )


# DELETE
@protected_router.delete("/{game_id}", status_code=204, responses={401: {"description": "Authentication required"}})
def delete_game(
        db: Annotated[Session, Depends(get_db)],
        game_id: str,
        current_user: User = auth_required()
):
    db_game = db.query(Game).filter(Game.id == game_id).first()
    if not db_game:
        raise GAME_NOT_FOUND_EXCEPTION

    if db_game.contributor_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not allowed to delete this game")

    db.delete(db_game)
    db.commit()
    return None
