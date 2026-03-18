from typing import List

from pydantic import BaseModel

from src.models.enums.age_rating_enum import AgeRatingEnum
from src.models.enums.duration_enum import DurationEnum
from src.models.enums.equipment_enum import GameEquipmentEnum
from src.models.enums.game_difficulty_enum import GameDifficultyEnum
from src.models.enums.game_theme_enum import GameThemeEnum
from src.models.enums.game_type_enum import GameTypeEnum


class GameMetadata(BaseModel):
    game_types: List[GameTypeEnum]
    age_ratings: List[AgeRatingEnum]
    game_equipment: List[GameEquipmentEnum]
    game_themes: List[GameThemeEnum]
    durations: List[DurationEnum]
    difficulty: List[GameDifficultyEnum]
