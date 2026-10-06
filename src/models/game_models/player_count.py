from pydantic import BaseModel, Field

class PlayerCount(BaseModel):
    min_players: int = Field(..., gt=0)
    max_players: int = Field(..., gt=0, lt=100)