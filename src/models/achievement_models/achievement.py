from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from src.models.enums.achievement_enum import AchievementTypeEnum


class AchievementRead(BaseModel):
    achievement_type: AchievementTypeEnum
    achieved: bool
    achieved_at: Optional[datetime] = None


class AchievementSignalRequest(BaseModel):
    achievement_type: AchievementTypeEnum
