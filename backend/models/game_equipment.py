from pydantic import BaseModel


class GameEquipmentBase(BaseModel):
    equipment_name: str