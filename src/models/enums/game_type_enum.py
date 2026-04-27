from enum import Enum


class GameTypeEnum(str, Enum):
    # Core formats
    card = "Card"
    dice = "Dice"
    board = "Board"

    # Social / party formats
    drinking = "Drinking"
    trivia = "Trivia"
    word = "Word"

    # Physical / movement
    physical = "Physical"

    # Thinking / structure
    strategy = "Strategy"
    logic = "Logic"
    puzzle = "Puzzle"

    # Role-based / imagination
    roleplay = "Roleplay"

    # Guessing & deception
    guessing = "Guessing"
    bluffing = "Bluffing"

    # Drawing / creativity
    drawing = "Drawing"

    # Real-world / improvised
    improv = "Improv"

    other = "Other"
