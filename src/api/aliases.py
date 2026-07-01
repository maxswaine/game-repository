from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.users import get_current_active_user, require_admin
from src.core.exceptions import GAME_NOT_FOUND_EXCEPTION
from src.db.database import get_db
from src.db.tables import Game, GameAlias
from src.models.alias_models.alias import AliasCreate, AliasRead, AliasPatch
from src.services.embedder import build_game_text, embed_text, embedding_to_json

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


@admin_router.get("/aliases", response_model=list[AliasRead])
def list_pending_aliases(
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    return db.query(GameAlias).filter(GameAlias.status == "pending").all()


@admin_router.patch("/aliases/{alias_id}", response_model=AliasRead)
def review_alias(
    alias_id: str,
    body: AliasPatch,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    if body.status not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="status must be 'approved' or 'rejected'")
    alias = db.query(GameAlias).filter(GameAlias.id == alias_id).first()
    if not alias:
        raise HTTPException(status_code=404, detail="Alias not found")

    alias.status = body.status
    alias.reviewed_by = current_user.id
    alias.reviewed_at = datetime.now(timezone.utc)
    db.commit()

    if body.status == "approved":
        _re_embed_game_with_aliases(db, alias.game_id)

    db.refresh(alias)
    return alias


def _re_embed_game_with_aliases(db: Session, game_id: str) -> None:
    """Re-embed the game including its newly approved alias. Best-effort."""
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        return
    approved_aliases = [
        a.alias
        for a in db.query(GameAlias)
        .filter(GameAlias.game_id == game_id, GameAlias.status == "approved")
        .all()
    ]
    try:
        text = build_game_text(game, aliases=approved_aliases)
        game.embedding = embedding_to_json(embed_text(text))
        db.commit()
    except Exception:
        pass
