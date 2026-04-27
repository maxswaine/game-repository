from enum import Enum


class GameSettingEnum(str, Enum):
    # Occasion / setting
    date_night = "Date Night"
    first_date = "First Date"
    party = "Party"
    house_party = "House Party"
    dinner_party = "Dinner Party"
    game_night = "Game Night"
    pub = "Pub / Bar"
    late_night = "Late Night"
    holiday = "Holiday"
    camping = "Camping"
    road_trip = "Road Trip"
    outdoor = "Outdoor"
    classroom = "Classroom"
    icebreaker = "Icebreaker"
    work_appropriate = "Work Appropriate"
    family_friendly = "Family Friendly"
    adults_only = "Adults Only"

    # Drinking
    drinking_optional = "Drinking Optional"
    drinking_required = "Drinking Required"

    # Emotional tone
    funny = "Funny"
    silly = "Silly"
    wholesome = "Wholesome"
    romantic = "Romantic"
    spicy = "Spicy"
    awkward = "Awkward"
    dramatic = "Dramatic"
    tense = "Tense"
    argumentative = "Argumentative"
    nostalgic = "Nostalgic"
    daring = "Daring"
    dark = "Dark"
    absurd = "Absurd"

    # Energy / vibe
    chill = "Chill"
    casual = "Casual"
    intense = "Intense"
    chaotic = "Chaotic"
    active = "Active"
    friendship_ruiner = "Friendship Ruiner"
    quick = "Quick"

    # Social format
    competitive = "Competitive"
    cooperative = "Cooperative"
    team = "Team"
    solo_friendly = "Solo Friendly"
    two_player = "Two Player"
    large_group = "Large Group"
    mixed_ages = "Mixed Ages"

    # Interaction style
    creative = "Creative"
    storytelling = "Storytelling"
    conversation = "Conversation"
    roleplay = "Roleplay"
