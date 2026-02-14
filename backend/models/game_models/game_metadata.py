from typing import List

from pydantic import BaseModel

from backend.models.enums.age_rating_enum import AgeRatingEnum
from backend.models.enums.duration_enum import DurationEnum
from backend.models.enums.equipment_enum import GameEquipmentEnum
from backend.models.enums.game_difficulty_enum import GameDifficultyEnum
from backend.models.enums.game_theme_enum import GameThemeEnum
from backend.models.enums.game_type_enum import GameTypeEnum


class GameMetadata(BaseModel):
    game_types: List[GameTypeEnum]
    age_ratings: List[AgeRatingEnum]
    game_equipment: List[GameEquipmentEnum]
    game_themes: List[GameThemeEnum]
    durations: List[DurationEnum]
    difficulty: List[GameDifficultyEnum]
