from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.models.enums.game_difficulty_enum import GameDifficultyEnum
from src.models.enums.game_icon_enum import GameIconEnum
from src.models.enums.game_type_enum import GameTypeEnum
from src.models.game_models.player_count import PlayerCount
from src.models.game_models.game_photo import GamePhotoRead
from src.models.user_models.user import UserPublicRead


class GameBase(BaseModel):
    name: str = Field(max_length=100)
    description: str = Field(max_length=2000)
    game_type: GameTypeEnum
    player_count: PlayerCount
    duration: str
    difficulty: Optional[GameDifficultyEnum] = None
    equipment: List[str]
    objective: str = Field(max_length=2000)
    setup: str = Field(max_length=2000)
    rules: str = Field(max_length=5000)
    image_url: Optional[str] = None
    icon: Optional[GameIconEnum] = None
    is_public: bool
    is_whats_that_game_certified: bool = False
    game_setting: Optional[List[str]] = None


class GameCreate(GameBase):
    aliases: list[str] = []


class GameRead(GameBase):
    id: str
    upvotes: int
    contributor: UserPublicRead
    created_at: datetime
    aliases: list[str] = []
    has_adult_content: bool = False
    liked_by_me: bool = False
    photos: list[GamePhotoRead] = []

    model_config = ConfigDict(from_attributes=True)


class GameUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=2000)
    game_type: Optional[GameTypeEnum] = None
    min_players: Optional[int] = None
    max_players: Optional[int] = None
    duration: Optional[str] = None
    difficulty: Optional[GameDifficultyEnum] = None
    equipment: Optional[List[str]] = None
    icon: Optional[GameIconEnum] = None
    is_public: Optional[bool] = None
    objective: Optional[str] = Field(None, max_length=2000)
    setup: Optional[str] = Field(None, max_length=2000)
    rules: Optional[str] = Field(None, max_length=5000)
    game_setting: Optional[List[str]] = None
