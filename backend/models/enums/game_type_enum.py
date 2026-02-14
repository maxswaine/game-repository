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
    dexterity = "Dexterity"
    reflex = "Reflex"

    # Thinking / structure
    strategy = "Strategy"
    logic = "Logic"
    puzzle = "Puzzle"

    # Role-based / imagination
    roleplay = "Roleplay"
    acting = "Acting"
    storytelling = "Storytelling"

    # Guessing & deception
    guessing = "Guessing"
    bluffing = "Bluffing"

    # Drawing / creativity
    drawing = "Drawing"
    creative = "Creative"

    # Casual / lightweight
    casual = "Casual"
    filler = "Filler"

    # Competitive structure
    competitive = "Competitive"
    cooperative = "Cooperative"
    team = "Team"

    # Real-world / improvised
    improv = "Improv"
    no_equipment = "No Equipment"
