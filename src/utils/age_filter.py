from __future__ import annotations

import re
from datetime import date
from typing import Optional

from src.models.enums.age_rating_enum import AgeRatingEnum

_ALL_RATINGS = list(AgeRatingEnum)
_UP_TO_16 = [r for r in AgeRatingEnum if r != AgeRatingEnum.age_18]

_ADULT_GAME_TYPES = {"Drinking"}

_ADULT_SETTINGS = {"Adults Only", "Drinking Required", "Drinking Optional", "Spicy"}

_ADULT_KEYWORDS = [
    "take a drink", "takes a drink", "everyone drinks", "drinking game",
    "take a shot", "takes a shot", "down a shot", "shotgun",
    "drink if", "drink when", "sip if", "sip when",
    "strip", "vodka", "tequila", "rum",
    "naked", "nude", "sexual", "erotic",
]

_LEET_MAP = str.maketrans(
    {'0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's', '7': 't', '@': 'a', '$': 's', '!': 'i'}
)

_PROFANITY_PATTERNS = [
    r"\bfuck\w*\b",
    r"\bshit\w*\b",
    r"\bcunt\w*\b",
    r"\bcock\b",
    r"\bass\b",
    r"\bbitch\w*\b",
    r"\bpussy\b",
    r"\basshole\b",
    r"\bwanker\b",
    r"\btwat\b",
    r"\bwhore\b",
    r"\bslut\w*\b",
    r"\bmotherfuck\w*\b",
]

_COMPILED_PROFANITY = [re.compile(p, re.IGNORECASE) for p in _PROFANITY_PATTERNS]


def _normalize(text: str) -> str:
    return text.lower().translate(_LEET_MAP)


def detect_profanity(text: str) -> bool:
    normalized = _normalize(text)
    return any(p.search(normalized) for p in _COMPILED_PROFANITY)


def detect_adult_content(game_type: str, settings: list[str], text: str) -> bool:
    if game_type in _ADULT_GAME_TYPES:
        return True
    if any(s in _ADULT_SETTINGS for s in settings):
        return True
    lowered = _normalize(text)
    return any(kw in lowered for kw in _ADULT_KEYWORDS)


def allowed_age_ratings(date_of_birth: Optional[date]) -> list[AgeRatingEnum]:
    if date_of_birth is None:
        return _UP_TO_16

    today = date.today()
    age = (today - date_of_birth).days // 365

    if age >= 18:
        return _ALL_RATINGS
    if age >= 16:
        return _UP_TO_16
    if age >= 12:
        return [AgeRatingEnum.all_ages, AgeRatingEnum.age_3, AgeRatingEnum.age_7, AgeRatingEnum.age_12]
    if age >= 7:
        return [AgeRatingEnum.all_ages, AgeRatingEnum.age_3, AgeRatingEnum.age_7]
    if age >= 3:
        return [AgeRatingEnum.all_ages, AgeRatingEnum.age_3]
    return [AgeRatingEnum.all_ages]
