from typing import List

from pydantic import BaseModel

from src.models.enums.duration_enum import DurationEnum
from src.models.enums.equipment_enum import GameEquipmentEnum
from src.models.enums.game_difficulty_enum import GameDifficultyEnum
from src.models.enums.game_icon_enum import GameIconEnum
from src.models.enums.game_setting_enum import GameSettingEnum
from src.models.enums.game_type_enum import GameTypeEnum
from src.models.enums.user_segment_enum import UserSegmentEnum


class GameMetadata(BaseModel):
    game_types: List[GameTypeEnum]
    game_equipment: List[GameEquipmentEnum]
    game_settings: List[GameSettingEnum]
    durations: List[DurationEnum]
    difficulty: List[GameDifficultyEnum]
    game_icons: List[GameIconEnum]
    user_segments: List[UserSegmentEnum]
