from enum import Enum

class AgeRating(str, Enum):
    age_3 = "3+"
    age_7 = "7+"
    age_12 = "12+"
    age_16 = "16+"
    age_18 = "18+"