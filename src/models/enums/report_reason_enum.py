from enum import Enum


class GameReportReasonEnum(str, Enum):
    inappropriate_content = "Inappropriate Content"
    adult_content = "Adult Content"
    spam = "Spam"
    inaccurate = "Inaccurate"
    other = "Other"
