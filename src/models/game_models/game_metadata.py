from typing import List

from pydantic import BaseModel

from src.models.enums.duration_enum import DurationEnum
from src.models.enums.equipment_enum import GameEquipmentEnum
from src.models.enums.game_difficulty_enum import GameDifficultyEnum
from src.models.enums.game_setting_enum import GameSettingEnum
from src.models.enums.game_type_enum import GameTypeEnum


class GameMetadata(BaseModel):
    game_types: List[GameTypeEnum]
    game_equipment: List[GameEquipmentEnum]
    game_settings: List[GameSettingEnum]
    durations: List[DurationEnum]
    difficulty: List[GameDifficultyEnum]
