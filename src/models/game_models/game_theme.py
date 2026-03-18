from pydantic import BaseModel

from src.models.enums.game_theme_enum import GameThemeEnum


class GameThemeBase(BaseModel):
    theme_name: GameThemeEnum