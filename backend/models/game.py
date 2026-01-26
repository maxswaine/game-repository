from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from backend.models.enums import AgeRating, GameType
from backend.models.game_equipment import GameEquipmentBase
from backend.models.game_theme import GameThemeBase
from backend.models.player_count import PlayerCount
from backend.models.user import UserPublicRead


class GameBase(BaseModel):
    name: str
    description: str
    age_rating: AgeRating
    game_type: GameType
    player_count: PlayerCount
    duration: str
    equipment: List[GameEquipmentBase]
    themes: List[GameThemeBase]
    rules: str
    image_url: Optional[str] = None
    is_public: bool


class GameCreate(GameBase):
    pass


class GameRead(GameBase):
    upvotes: int
    downvotes: int
    contributor: UserPublicRead
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GameUpdate(BaseModel):
    name: Optional[str] = None
    game_type: Optional[GameType] = None
    age_rating: Optional[AgeRating] = None
    min_players: Optional[int] = None
    max_players: Optional[int] = None
    duration: Optional[str] = None
    equipment: Optional[List[GameEquipmentBase]] = None
    themes: Optional[List[GameThemeBase]] = None
    is_public: Optional[bool] = None
