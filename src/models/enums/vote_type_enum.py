from enum import Enum

class Vote(str, Enum):
    upvote = "upvote"
    downvote = "downvote"