from pydantic import BaseModel, Field

from src.models.game_models.game import GameRead


class GameSearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500,
                       description="Natural language description of the game you're looking for")
    limit: int = Field(default=5, ge=1, le=20)


class GameSearchResult(GameRead):
    score: float = Field(..., description="Similarity score 0-1, higher is more relevant")
