from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from src.db.tables import GameTypeEnum
from src.models.enums.age_rating_enum import AgeRatingEnum
from src.models.game_models.player_count import PlayerCount
from src.models.user_models.user import UserPublicRead


class GameBase(BaseModel):
    name: str
    description: str
    age_rating: AgeRatingEnum
    game_type: GameTypeEnum
    player_count: PlayerCount
    duration: str
    equipment: List[str]
    objective: str
    setup: str
    rules: str
    image_url: Optional[str] = None
    is_public: bool
    is_whats_that_game_certified: bool = False
    game_setting: Optional[List[str]] = None


class GameCreate(GameBase):
    pass


class GameRead(GameBase):
    id: str
    upvotes: int
    contributor: UserPublicRead
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GameUpdate(BaseModel):
    name: Optional[str] = None
    game_type: Optional[GameTypeEnum] = None
    age_rating: Optional[AgeRatingEnum] = None
    min_players: Optional[int] = None
    max_players: Optional[int] = None
    duration: Optional[str] = None
    equipment: Optional[List[str]] = None
    is_public: Optional[bool] = None
    objective: Optional[str] = None
    setup: Optional[str] = None
    rules: Optional[str] = None
    game_setting: Optional[List[str]] = None


class GameUpdateAdmin(GameUpdate):
    is_whats_that_game_certified: Optional[bool] = None
