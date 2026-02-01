from enum import Enum

class GameThemeEnum(str, Enum):
    # Social & interaction
    guessing = "guessing"
    bluffing = "bluffing"
    roleplay = "roleplay"
    acting = "acting"
    storytelling = "storytelling"
    conversation = "conversation"
    icebreaker = "icebreaker"
    debate = "debate"
    deception = "deception"
    negotiation = "negotiation"

    # Skill & thinking
    strategy = "strategy"
    logic = "logic"
    memory = "memory"
    dexterity = "dexterity"
    reflex = "reflex"
    pattern_recognition = "pattern_recognition"
    problem_solving = "problem_solving"
    creativity = "creativity"
    lateral_thinking = "lateral_thinking"

    # Competitive tone
    competitive = "competitive"
    cooperative = "cooperative"
    team = "team"
    solo_friendly = "solo_friendly"
    elimination = "elimination"
    comeback = "comeback"

    # Risk & chaos
    luck = "luck"
    push_your_luck = "push_your_luck"
    chaos = "chaos"
    high_variance = "high_variance"
    gambling_adjacent = "gambling_adjacent"

    # Drinking / party energy
    drinking_optional = "drinking_optional"
    drinking_required = "drinking_required"
    endurance = "endurance"
    penalty_based = "penalty_based"
    challenge_based = "challenge_based"

    # Emotional / vibe
    funny = "funny"
    silly = "silly"
    tense = "tense"
    wholesome = "wholesome"
    spicy = "spicy"
    awkward = "awkward"
    dramatic = "dramatic"

    # Weight / mood
    casual = "casual"
    filler = "filler"
    fast = "fast"
    chill = "chill"
    intense = "intense"
    late_night = "late_night"
    family_friendly = "family_friendly"
    adults_only = "adults_only"
    friendship_ruiner = "friendship_ruiner"
