from datetime import datetime
from pydantic import BaseModel, ConfigDict


class AliasCreate(BaseModel):
    alias: str


class AliasRead(BaseModel):
    id: str
    game_id: str
    alias: str
    suggested_by: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AliasPatch(BaseModel):
    status: str  # "approved" | "rejected"
