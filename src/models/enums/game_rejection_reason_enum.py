from enum import Enum


class GameRejectionReasonEnum(str, Enum):
    profanity = "Profanity"
    inappropriate_content = "Inappropriate Content"
    adult_content_unflagged = "Adult Content Not Flagged"
    duplicate = "Duplicate Submission"
    low_quality = "Low Quality / Unclear Rules"
    spam = "Spam"
    other = "Other"
