import re
from typing import List, Annotated

import numpy as np

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from src.api.games import map_game_to_read, _get_liked_ids, _apply_age_content_filter
from src.api.users import get_current_user_optional
from src.db.database import get_db
from src.db.tables import Game, GameEquipment, User
from src.models.enums.equipment_enum import GameEquipmentEnum
from src.models.game_models.game_search import GameSearchRequest, GameSearchResult
from src.services.embedder import embed_query, json_to_embedding

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

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}
_NUMBER_TOKEN = r"(?:\d{1,3}|" + "|".join(_NUMBER_WORDS) + r")"
_PLAYER_COUNT_RE = re.compile(
    rf"\b({_NUMBER_TOKEN})\s+(?:players?|people|person|friends|guests)\b"
)
_OF_US_RE = re.compile(rf"\b({_NUMBER_TOKEN})\s+of\s+us\b")


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


def _extract_player_count(query: str) -> int | None:
    """Pull an explicit headcount ('6 people', '4 of us') out of free-text search queries."""
    q = query.lower()
    for pattern in (_PLAYER_COUNT_RE, _OF_US_RE):
        match = pattern.search(q)
        if match:
            token = match.group(1)
            count = _NUMBER_WORDS.get(token, None)
            if count is None:
                count = int(token)
            if 1 <= count <= 100:
                return count
    return None


def _has_equipment_in(values: set[str]):
    """EXISTS subquery: this game has at least one equipment row in `values`."""
    return (
        select(GameEquipment.game_id)
        .where(
            GameEquipment.game_id == Game.id,
            GameEquipment.equipment_name.in_(values),
        )
        .exists()
    )


def _apply_hard_filters(query, text: str, player_count: int | None = None):
    """
    Drop games that cannot satisfy explicit constraints in the query text.

    Applied in SQL rather than over loaded objects so the ranking step only
    sees candidates that already qualify, and so a filtered-out game never
    costs us its embedding over the wire.
    """
    if _wants_no_equipment(text):
        # "no equipment" means every row is the none sentinel, i.e. there is
        # no row that is anything else.
        query = query.filter(
            ~_has_equipment_in({e.value for e in GameEquipmentEnum if e != GameEquipmentEnum.none})
        )
    else:
        excluded = _excluded_equipment_from_negations(text)
        if excluded:
            query = query.filter(~_has_equipment_in({e.value for e in excluded}))

    count = player_count if player_count is not None else _extract_player_count(text)
    if count is not None:
        query = query.filter(Game.min_players <= count, Game.max_players >= count)

    return query


def _rank(rows: list[tuple[str, str]], query_vector) -> tuple[list[str], list[float]]:
    """
    Score every candidate against the query in one matmul.

    Rows whose stored embedding is unparseable or the wrong width are skipped
    rather than failing the request, matching the per-game try/except this
    replaces.
    """
    query_v = np.asarray(query_vector, dtype=np.float32)

    ids: list[str] = []
    vectors: list[list[float]] = []
    for game_id, raw in rows:
        try:
            vector = json_to_embedding(raw)
        except Exception:
            continue
        if len(vector) != query_v.shape[0]:
            continue
        ids.append(game_id)
        vectors.append(vector)

    if not ids:
        return [], []

    matrix = np.asarray(vectors, dtype=np.float32)
    # Keep the norms rather than assuming unit vectors: text-embedding-3-small
    # returns them normalised, but a model swap or a hand-written vector would
    # silently skew scores. Vectorised, this costs ~nothing.
    denominator = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query_v)
    scores = np.divide(
        matrix @ query_v,
        denominator,
        out=np.zeros(len(ids), dtype=np.float32),
        where=denominator > 0,
    )
    return ids, scores


@router.post("/", response_model=List[GameSearchResult], status_code=200,
             responses={503: {"description": "Embedding service unavailable"}})
def semantic_search(
        request: GameSearchRequest,
        db: Annotated[Session, Depends(get_db)],
        current_user: Annotated[User | None, Depends(get_current_user_optional)] = None,
):
    try:
        query_vector = embed_query(request.query)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Embedding service unavailable: {str(e)}")

    # Pass 1: ids and embeddings only. Hydrating the whole catalogue with its
    # relations to return a handful of rows was the bulk of this endpoint's
    # cost, so the heavy load is deferred until the winners are known.
    candidates = _apply_age_content_filter(
        db.query(Game.id, Game.embedding).filter(
            Game.is_public == True,
            Game.status == "approved",
            Game.embedding.isnot(None),
        ),
        current_user,
    )
    rows = _apply_hard_filters(candidates, request.query, request.player_count).all()

    if not rows:
        return []

    ids, scores = _rank(rows, query_vector)
    if not ids:
        return []

    # Stable, so games on an identical score keep their relative order the way
    # the previous list.sort(reverse=True) did.
    top_indexes = np.argsort(-scores, kind="stable")[:request.limit]
    top_ids = [ids[i] for i in top_indexes]

    # Pass 2: full objects, for the winners only.
    games_by_id = {
        game.id: game
        for game in db.query(Game)
        .options(
            joinedload(Game.equipment_items),
            joinedload(Game.setting_items),
            joinedload(Game.contributor),
            joinedload(Game.alias_objects),
            joinedload(Game.photos),
        )
        .filter(Game.id.in_(top_ids))
        .all()
    }

    liked_ids = _get_liked_ids(db, current_user.id) if current_user else None
    return [
        GameSearchResult(
            **map_game_to_read(games_by_id[game_id], liked_ids).model_dump(),
            score=round(float(scores[index]), 4),
        )
        for index, game_id in zip(top_indexes, top_ids)
        if game_id in games_by_id
    ]
