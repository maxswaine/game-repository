from enum import Enum


class GameTypeEnum(str, Enum):
    # Core formats
    card = "Card"
    dice = "Dice"

    # Social / party formats
    drinking = "Drinking"
    trivia = "Trivia"
    word = "Word"

    # Physical / movement
    physical = "Physical"

    # Thinking / structure
    strategy = "Strategy"

    # Guessing & deception
    guessing = "Guessing"
    acting = "Acting"

    # Drawing / creativity
    drawing = "Drawing"

    music = "Music"

    other = "Other"