from enum import Enum


class SortByEnum(str, Enum):
    recent = "recent"
    trending = "trending"
    recommended = "recommended"
