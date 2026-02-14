from typing import List

import pycountry
from fastapi import APIRouter
from pydantic import BaseModel

from backend.models.enums.age_rating_enum import AgeRatingEnum
from backend.models.enums.equipment_enum import GameEquipmentEnum
from backend.models.enums.game_theme_enum import GameThemeEnum
from backend.models.enums.game_type_enum import GameTypeEnum
from backend.models.game_models.game_metadata import GameMetadata

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
        age_ratings=[ar.value for ar in AgeRatingEnum],
        game_themes=[gth.value for gth in GameThemeEnum],
        game_equipment=[eq.value for eq in GameEquipmentEnum]
    )
