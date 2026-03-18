from pydantic import BaseModel

from src.models.enums.equipment_enum import GameEquipmentEnum


class GameEquipmentBase(BaseModel):
    equipment_name: GameEquipmentEnum