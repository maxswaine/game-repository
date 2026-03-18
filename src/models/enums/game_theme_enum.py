from enum import Enum

class GameThemeEnum(str, Enum):
    # Social & interaction
    guessing = "Guessing"
    bluffing = "Bluffing"
    roleplay = "Roleplay"
    acting = "Acting"
    storytelling = "Storytelling"
    conversation = "Conversation"
    icebreaker = "Icebreaker"
    debate = "Debate"
    deception = "Deception"
    negotiation = "Negotiation"

    # Skill & thinking
    strategy = "Strategy"
    logic = "Logic"
    memory = "Memory"
    dexterity = "Dexterity"
    reflex = "Reflex"
    pattern_recognition = "Pattern Recognition"
    problem_solving = "Problem Solving"
    creativity = "Creativity"
    lateral_thinking = "Lateral Thinking"

    # Competitive tone
    competitive = "Competitive"
    cooperative = "Cooperative"
    team = "Team"
    solo_friendly = "Solo Friendly"
    elimination = "Elimination"
    comeback = "Comeback"

    # Risk & chaos
    luck = "Luck"
    push_your_luck = "Push Your Luck"
    chaos = "Chaos"
    high_variance = "High Variance"
    gambling_adjacent = "Gambling Adjacent"

    # Drinking / party energy
    drinking_optional = "Drinking Optional"
    drinking_required = "Drinking Required"
    endurance = "Endurance"
    penalty_based = "Penalty Based"
    challenge_based = "Challenge Based"

    # Emotional / vibe
    funny = "Funny"
    silly = "Silly"
    tense = "Tense"
    wholesome = "Wholesome"
    spicy = "Spicy"
    awkward = "Awkward"
    dramatic = "Dramatic"

    # Weight / mood
    casual = "Casual"
    filler = "Filler"
    fast = "Fast"
    chill = "Chill"
    intense = "Intense"
    late_night = "Late Night"
    family_friendly = "Family Friendly"
    adults_only = "Adults Only"
    friendship_ruiner = "Friendship Ruiner"
