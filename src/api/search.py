import re
from typing import List, Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from src.api.games import map_game_to_read, _get_liked_ids
from src.api.users import get_current_user_optional
from src.db.database import get_db
from src.db.tables import Game, User
from src.models.enums.equipment_enum import GameEquipmentEnum
from src.models.game_models.game_search import GameSearchRequest, GameSearchResult
from src.services.embedder import embed_text, cosine_similarity, json_to_embedding

router = APIRouter()

_NO_EQUIPMENT_PHRASES = [
    "no equipment", "without equipment", "no gear", "nothing needed",
    "hands only", "empty handed", "no props", "no materials", "no items",
    "no stuff", "need nothing",
]

_STOPWORDS = {"a", "an", "of", "the", "and", "to", "for"}

_NEGATION_RE = re.compile(
    r"(?:no|without|never|don'?t (?:want|need|have)(?: any)?|not any) ([a-z]+(?: [a-z]+)?)"
)


def _fold_plural(word: str) -> str:
    return word[:-1] if word.endswith("s") and len(word) > 3 else word


def _build_equipment_keyword_index() -> dict:
    index: dict[str, set] = {}
    for member in GameEquipmentEnum:
        words = re.split(r"[\s-]+", member.value.lower())
        for word in words:
            if word in _STOPWORDS or not word:
                continue
            key = _fold_plural(word)
            index.setdefault(key, set()).add(member)
    return index


_EQUIPMENT_KEYWORD_INDEX = _build_equipment_keyword_index()


def _wants_no_equipment(query: str) -> bool:
    q = query.lower()
    return any(phrase in q for phrase in _NO_EQUIPMENT_PHRASES)


def _excluded_equipment_from_negations(query: str) -> set:
    """Resolve every 'no/without <item>' phrase in the query to specific equipment enum members."""
    excluded: set = set()
    for phrase in _NEGATION_RE.findall(query.lower()):
        if phrase in _EQUIPMENT_KEYWORD_INDEX:
            excluded |= _EQUIPMENT_KEYWORD_INDEX[phrase]
            continue
        for word in phrase.split(" "):
            key = _fold_plural(word)
            if key in _EQUIPMENT_KEYWORD_INDEX:
                excluded |= _EQUIPMENT_KEYWORD_INDEX[key]
    return excluded


def _apply_hard_filters(games: list, query: str) -> list:
    """Remove games that cannot satisfy explicit constraints in the query."""
    if _wants_no_equipment(query):
        no_equipment_values = {GameEquipmentEnum.none.value, GameEquipmentEnum.nothing.value}
        return [
            g for g in games
            if all(e.equipment_name in no_equipment_values for e in g.equipment_items)
        ]

    excluded = _excluded_equipment_from_negations(query)
    if excluded:
        excluded_values = {e.value for e in excluded}
        games = [
            g for g in games
            if not any(e.equipment_name in excluded_values for e in g.equipment_items)
        ]
    return games


@router.post("/", response_model=List[GameSearchResult], status_code=200,
             responses={503: {"description": "Embedding service unavailable"}})
def semantic_search(
        request: GameSearchRequest,
        db: Annotated[Session, Depends(get_db)],
        current_user: Annotated[User | None, Depends(get_current_user_optional)] = None,
):
    try:
        query_vector = embed_text(request.query)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Embedding service unavailable: {str(e)}")

    games = (
        db.query(Game)
        .options(
            joinedload(Game.equipment_items),
            joinedload(Game.setting_items),
            joinedload(Game.contributor),
            joinedload(Game.alias_objects),
            joinedload(Game.photos),
        )
        .filter(Game.is_public == True, Game.embedding.isnot(None))
        .all()
    )

    if not games:
        return []

    games = _apply_hard_filters(games, request.query)

    if not games:
        return []

    scored = []
    for game in games:
        try:
            game_vector = json_to_embedding(game.embedding)
            score = cosine_similarity(query_vector, game_vector)
            scored.append((score, game))
        except Exception:
            continue

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:request.limit]

    liked_ids = _get_liked_ids(db, current_user.id) if current_user else None
    return [
        GameSearchResult(**map_game_to_read(game, liked_ids).model_dump(), score=round(score, 4))
        for score, game in top
    ]
