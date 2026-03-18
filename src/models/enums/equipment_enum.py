from enum import Enum

class GameEquipmentEnum(str, Enum):
    # --------------------
    # None / Minimal
    # --------------------
    none = "None"
    nothing = "Nothing"

    # --------------------
    # Cards
    # --------------------
    standard_deck = "Standard Deck"
    jokers = "Jokers"
    multiple_decks = "Multiple Decks"
    tarot_deck = "Tarot Deck"
    improvised_cards = "Improvised Cards"
    less_than_a_deck = "Less Than a Deck"
    uno_deck = "UNO Deck"

    # --------------------
    # Dice
    # --------------------
    six_sided_dice = "Six-Sided Dice"
    multiple_dice = "Multiple Dice"
    dice_cup = "Dice Cup"
    shaker = "Shaker"
    phone_dice_app = "Phone Dice App"

    # --------------------
    # Coins & Small Counters
    # --------------------
    coins = "Coins"
    bottle_caps = "Bottle Caps"
    tokens = "Tokens"
    buttons = "Buttons"
    beads = "Beads"
    stones = "Stones"
    pebbles = "Pebbles"
    poker_chips = "Poker Chips"
    matchsticks = "Matchsticks"
    toothpicks = "Toothpicks"
    straws = "Straws"

    # --------------------
    # Paper & Writing
    # --------------------
    paper = "Paper"
    pen = "Pen"
    pencil = "Pencil"
    napkins = "Napkins"
    notebook = "Notebook"
    sticky_notes = "Sticky Notes"
    index_cards = "Index Cards"
    whiteboard = "Whiteboard"
    chalkboard = "Chalkboard"
    marker = "Marker"
    chalk = "Chalk"

    # --------------------
    # Timers & Randomisers
    # --------------------
    phone_timer = "Phone Timer"
    stopwatch = "Stopwatch"
    hourglass = "Hourglass"
    countdown_app = "Countdown App"
    random_number_generator = "Random Number Generator"
    random_word_generator = "Random Word Generator"
    spinner = "Spinner"

    # --------------------
    # Cups, Containers & Surfaces
    # --------------------
    cups = "Cups"
    mugs = "Mugs"
    glasses = "Glasses"
    shot_glasses = "Shot Glasses"
    bowl = "Bowl"
    plate = "Plate"
    tray = "Tray"
    coasters = "Coasters"

    # --------------------
    # Tables & Space
    # --------------------
    table = "Table"
    flat_surface = "Flat Surface"
    floor_space = "Floor Space"
    wall_space = "Wall Space"

    # --------------------
    # Body / Physical Play
    # --------------------
    players_hands = "Players' Hands"
    players_bodies = "Players' Bodies"
    fingers = "Fingers"
    gestures = "Gestures"
    clapping = "Clapping"
    balance = "Balance"
    reflexes = "Reflexes"

    # --------------------
    # Verbal / Cognitive
    # --------------------
    voice = "Voice"
    memory = "Memory"
    imagination = "Imagination"
    trivia_knowledge = "Trivia Knowledge"

    # --------------------
    # Phones / Tech (Very Common)
    # --------------------
    smartphone = "Smartphone"
    shared_phone = "Shared Phone"
    camera = "Camera"
    flashlight = "Flashlight"
    music_player = "Music Player"
    speaker = "Speaker"
    app = "App"

    # --------------------
    # Drinking-Game Adjacent
    # --------------------
    drinks = "Drinks"
    empty_glasses = "Empty Glasses"
    drink_tokens = "Drink Tokens"
    bar_menu = "Bar Menu"

    # --------------------
    # Improvised / Misc
    # --------------------
    towel = "Towel"
    cloth = "Cloth"
    playing_mat = "Playing Mat"
    rubber_bands = "Rubber Bands"
    string = "String"
    tape = "Tape"
    phone_flashlight = "Phone Flashlight"
