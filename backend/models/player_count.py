from pydantic import BaseModel, Field

class PlayerCount(BaseModel):
    min_players: int = Field(..., gt=1)
    max_players: int = Field(..., gt=1, lt=100)