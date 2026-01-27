from pydantic import BaseModel

from backend.models.enums.game_theme_enum import GameThemeEnum

class GameThemeBase(BaseModel):
    theme_name: GameThemeEnum