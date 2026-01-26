from enum import Enum

class GameType(str, Enum):
    card = "card"
    dice = "dice"
    board = "board"
    party = "party"
    strategy = "strategy"
    drinking = "drinking"


class AgeRating(str, Enum):
    age_3 = "3+"
    age_7 = "7+"
    age_12 = "12+"
    age_16 = "16+"
    age_18 = "18+"

class Role(str, Enum):
    admin = "admin"
    user = "user"

class Vote(str, Enum):
    upvote = "upvote"
    downvote = "downvote"