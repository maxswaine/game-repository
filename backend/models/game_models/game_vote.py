from pydantic import BaseModel

class GameVoteRead(BaseModel):
    game_id: str
    upvotes: int
    downvotes: int