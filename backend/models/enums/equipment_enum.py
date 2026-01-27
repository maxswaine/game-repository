from enum import Enum

class GameEquipmentEnum(str, Enum):
    # --------------------
    # None / Minimal
    # --------------------
    none = "none"
    nothing = "nothing"

    # --------------------
    # Cards
    # --------------------
    standard_deck = "standard_deck"
    jokers = "jokers"
    multiple_decks = "multiple_decks"
    tarot_deck = "tarot_deck"           # surprisingly common
    improvised_cards = "improvised_cards"
    less_than_a_deck= "less_than_a_deck"

    # --------------------
    # Dice
    # --------------------
    six_sided_dice = "six_sided_dice"
    multiple_dice = "multiple_dice"
    dice_cup = "dice_cup"
    shaker = "shaker"
    phone_dice_app = "phone_dice_app"

    # --------------------
    # Coins & Small Counters
    # --------------------
    coins = "coins"
    bottle_caps = "bottle_caps"
    tokens = "tokens"
    buttons = "buttons"
    beads = "beads"
    stones = "stones"
    pebbles = "pebbles"
    poker_chips = "poker_chips"
    matchsticks = "matchsticks"
    toothpicks = "toothpicks"
    straws = "straws"

    # --------------------
    # Paper & Writing
    # --------------------
    paper = "paper"
    pen = "pen"
    pencil = "pencil"
    napkins = "napkins"
    notebook = "notebook"
    sticky_notes = "sticky_notes"
    index_cards = "index_cards"
    whiteboard = "whiteboard"
    chalkboard = "chalkboard"
    marker = "marker"
    chalk = "chalk"

    # --------------------
    # Timers & Randomisers
    # --------------------
    phone_timer = "phone_timer"
    stopwatch = "stopwatch"
    hourglass = "hourglass"
    countdown_app = "countdown_app"
    random_number_generator = "random_number_generator"
    random_word_generator = "random_word_generator"

    # --------------------
    # Cups, Containers & Surfaces
    # --------------------
    cups = "cups"
    mugs = "mugs"
    glasses = "glasses"
    shot_glasses = "shot_glasses"
    bowl = "bowl"
    plate = "plate"
    tray = "tray"
    coasters = "coasters"

    # --------------------
    # Tables & Space
    # --------------------
    table = "table"
    flat_surface = "flat_surface"
    floor_space = "floor_space"
    wall_space = "wall_space"

    # --------------------
    # Body / Physical Play
    # --------------------
    players_hands = "players_hands"
    players_bodies = "players_bodies"
    fingers = "fingers"
    gestures = "gestures"
    clapping = "clapping"
    balance = "balance"
    reflexes = "reflexes"

    # --------------------
    # Verbal / Cognitive
    # --------------------
    voice = "voice"
    memory = "memory"
    imagination = "imagination"
    trivia_knowledge = "trivia_knowledge"

    # --------------------
    # Phones / Tech (Very Common)
    # --------------------
    smartphone = "smartphone"
    shared_phone = "shared_phone"
    camera = "camera"
    flashlight = "flashlight"
    music_player = "music_player"
    speaker = "speaker"
    app = "app"

    # --------------------
    # Drinking-Game Adjacent
    # --------------------
    drinks = "drinks"
    empty_glasses = "empty_glasses"
    drink_tokens = "drink_tokens"
    bar_menu = "bar_menu"

    # --------------------
    # Improvised / Misc
    # --------------------
    towel = "towel"
    cloth = "cloth"
    playing_mat = "playing_mat"
    rubber_bands = "rubber_bands"
    string = "string"
    tape = "tape"
    phone_flashlight = "phone_flashlight"