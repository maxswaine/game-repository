from enum import Enum


class AgeRatingEnum(str, Enum):
    all_ages = "All Ages"
    age_3 = "3+"
    age_7 = "7+"
    age_12 = "12+"
    age_16 = "16+"
    age_18 = "18+"