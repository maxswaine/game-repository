from pydantic import BaseModel

from backend.models.enums.equipment_enum import GameEquipmentEnum

class GameEquipmentBase(BaseModel):
    equipment_name: GameEquipmentEnum