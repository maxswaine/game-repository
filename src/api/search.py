from typing import List, Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from src.db.database import get_db
from src.db.tables import Game
from src.models.game_models.game_search import GameSearchRequest, GameSearchResult
from src.services.embedder import embed_text, cosine_similarity, json_to_embedding
from src.api.games import map_game_to_read

router = APIRouter()


@router.post("/", response_model=List[GameSearchResult], status_code=200)
def semantic_search(
        request: GameSearchRequest,
        db: Annotated[Session, Depends(get_db)],
):
    """
    Find games using natural language. Describe what you're looking for —
    e.g. "a quick card game for a pub with 4 friends" — and we'll return
    the closest matches using semantic similarity.

    Only games that have been indexed (have a stored embedding) are searched.
    """
    # Embed the user's query
    try:
        query_vector = embed_text(request.query)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Embedding service unavailable: {str(e)}")

    # Load all public games that have an embedding
    games = (
        db.query(Game)
        .options(
            joinedload(Game.equipment_items),
            joinedload(Game.setting_items),
            joinedload(Game.contributor),
        )
        .filter(Game.is_public == True, Game.embedding.isnot(None))
        .all()
    )

    if not games:
        return []

    # Score each game against the query
    scored = []
    for game in games:
        try:
            game_vector = json_to_embedding(game.embedding)
            score = cosine_similarity(query_vector, game_vector)
            scored.append((score, game))
        except Exception:
            continue  # skip games with malformed embeddings

    # Sort by score descending, take top N
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:request.limit]

    results = []
    for score, game in top:
        game_read = map_game_to_read(game)
        results.append(GameSearchResult(**game_read.model_dump(), score=round(score, 4)))

    return results
