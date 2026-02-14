from enum import Enum


class DurationEnum(str, Enum):
    under_5_min = "Under 5 minutes"
    five_to_10_min = "5-10 minutes"
    ten_to_15_min = "10-15 minutes"
    fifteen_to_30_min = "15-30 minutes"
    thirty_to_45_min = "30-45 minutes"
    forty_five_to_60_min = "45-60 minutes"
    one_to_two_hours = "1-2 hours"
    two_to_three_hours = "2-3 hours"
    over_three_hours = "Over 3 hours"
