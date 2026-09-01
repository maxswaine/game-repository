from typing import Optional

from pydantic import BaseModel, Field

from src.models.game_models.game import GameRead


class GameSearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500,
                       description="Natural language description of the game you're looking for")
    limit: int = Field(default=5, ge=1, le=20)
    player_count: Optional[int] = Field(
        default=None, ge=1, le=100,
        description="Explicit player count (e.g. from a UI control). Overrides any count detected in the query text."
    )


class GameSearchResult(GameRead):
    score: float = Field(..., description="Similarity score 0-1, higher is more relevant")
