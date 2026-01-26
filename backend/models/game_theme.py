from pydantic import BaseModel

class GameThemeBase(BaseModel):
    theme_name: str