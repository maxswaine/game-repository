from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.users import get_current_active_user
from src.core.exceptions import GAME_NOT_FOUND_EXCEPTION
from src.db.database import get_db
from src.db.tables import Game, GameAlias
from src.models.alias_models.alias import AliasCreate, AliasRead, AliasPatch

public_router = APIRouter()
admin_router = APIRouter()


@public_router.post("/{game_id}/aliases", response_model=AliasRead, status_code=201)
def suggest_alias(
    game_id: str,
    body: AliasCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    if not db.query(Game).filter(Game.id == game_id).first():
        raise GAME_NOT_FOUND_EXCEPTION
    alias = GameAlias(
        game_id=game_id,
        alias=body.alias,
        suggested_by=current_user.id,
    )
    db.add(alias)
    db.commit()
    db.refresh(alias)
    return alias


@public_router.get("/{game_id}/aliases", response_model=list[AliasRead])
def get_game_aliases(game_id: str, db: Session = Depends(get_db)):
    if not db.query(Game).filter(Game.id == game_id).first():
        raise GAME_NOT_FOUND_EXCEPTION
    return (
        db.query(GameAlias)
        .filter(GameAlias.game_id == game_id, GameAlias.status == "approved")
        .all()
    )
