from enum import Enum


class GameTypeEnum(str, Enum):
    # Core formats
    card = "card"
    dice = "dice"
    board = "board"

    # Social / party formats
    party = "party"
    drinking = "drinking"
    trivia = "trivia"
    word = "word"

    # Physical / movement
    physical = "physical"
    dexterity = "dexterity"
    reflex = "reflex"

    # Thinking / structure
    strategy = "strategy"
    logic = "logic"
    puzzle = "puzzle"

    # Role-based / imagination
    roleplay = "roleplay"
    acting = "acting"
    storytelling = "storytelling"

    # Guessing & deception
    guessing = "guessing"
    bluffing = "bluffing"

    # Drawing / creativity
    drawing = "drawing"
    creative = "creative"

    # Casual / lightweight
    casual = "casual"
    filler = "filler"

    # Competitive structure
    competitive = "competitive"
    cooperative = "cooperative"
    team = "team"

    # Real-world / improvised
    improv = "improv"
    no_equipment = "no_equipment"