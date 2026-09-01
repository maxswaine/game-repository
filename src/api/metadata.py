from typing import Annotated, List

import pycountry
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.db.tables import Game, GameEquipment, GameSetting
from src.models.enums.duration_enum import DurationEnum
from src.models.enums.equipment_enum import GameEquipmentEnum
from src.models.enums.game_difficulty_enum import GameDifficultyEnum
from src.models.enums.game_icon_enum import GameIconEnum
from src.models.enums.game_setting_enum import GameSettingEnum
from src.models.enums.game_type_enum import GameTypeEnum
from src.models.game_models.game_metadata import GameMetadata

router = APIRouter()


class Country(BaseModel):
    code: str
    name: str


class CountriesResponse(BaseModel):
    countries: List[Country]


@router.get("/countries", response_model=CountriesResponse)
def get_countries():
    countries = [
        Country(code=country.alpha_2, name=country.name)
        for country in pycountry.countries
    ]
    countries_sorted = sorted(countries, key=lambda x: x.name)
    return CountriesResponse(countries=countries_sorted)


@router.get("/metadata", response_model=GameMetadata, status_code=200)
def get_metadata():
    return GameMetadata(
        game_types=[gt.value for gt in GameTypeEnum],
        game_settings=[gth.value for gth in GameSettingEnum],
        game_equipment=[eq.value for eq in GameEquipmentEnum],
        durations=[d.value for d in DurationEnum],
        difficulty=[gd.value for gd in GameDifficultyEnum],
        game_icons=[gi.value for gi in GameIconEnum]
    )


@router.get("/existing-tags")
def get_existing_tags(db: Annotated[Session, Depends(get_db)]):
    settings = (
        db.query(GameSetting.setting_name)
        .join(Game, Game.id == GameSetting.game_id)
        .filter(Game.status == "approved")
        .distinct()
        .all()
    )
    equipment = (
        db.query(GameEquipment.equipment_name)
        .join(Game, Game.id == GameEquipment.game_id)
        .filter(Game.status == "approved")
        .distinct()
        .all()
    )
    settings_list = sorted({s[0].strip() for s in settings if s[0] and s[0].strip()})
    equipment_list = sorted({e[0].strip() for e in equipment if e[0] and e[0].strip()})
    return {"settings": settings_list, "equipment": equipment_list}
