from pydantic import BaseModel


class GameSettingModel(BaseModel):
    setting_name: str
