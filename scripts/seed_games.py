"""
Seed script — clears games-related tables and inserts games from the Excel spreadsheet.

Usage:
    DATABASE_URL=<railway_url> python scripts/seed_games.py
    or if .env is present it will be loaded automatically.
"""

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Load .env if present
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set.")
    sys.exit(1)

CONTRIBUTOR_ID = "c6293090-a478-4757-87a9-2562f7421128"

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

EXCEL_PATH = Path(__file__).parent.parent / "Game inputs.xlsx"
if not EXCEL_PATH.exists():
    EXCEL_PATH = Path.home() / "Downloads" / "Game inputs.xlsx"

# ── Type mapping ──────────────────────────────────────────────────────────────
GAME_TYPE_MAP = {
    "casual": "Card",
    "casual / prediction": "Card",
    "casual / cards": "Card",
    "casual / thinking": "Word",
    "casual / coin": "Other",
    "bluff / strategy": "Bluffing",
    "bluff / cards": "Bluffing",
    "party / drawing": "Drawing",
    "reflex / cards": "Card",
    "skill / coin": "Physical",
    "speaking / word": "Word",
    "speaking / guessing": "Guessing",
    "social / speaking": "Improv",
}

DURATION_MAP = {
    "under 5 minutes": "Under 5 minutes",
    "5-10 minutes": "5-10 minutes",
    "10-15 minutes": "10-15 minutes",
    "15-30 minutes": "15-30 minutes",
    "30-45 minutes": "30-45 minutes",
    "45-60 minutes": "45-60 minutes",
    "1-2 hours": "1-2 hours",
}

DIFFICULTY_MAP = {
    "easy": "Easy",
    "medium": "Medium",
    "hard": "Hard",
    "expert": "Expert",
}


def map_game_type(raw: str) -> str:
    return GAME_TYPE_MAP.get(str(raw).strip().lower(), "Other")


def map_duration(raw: str) -> str:
    return DURATION_MAP.get(str(raw).strip().lower(), str(raw).strip())


def map_difficulty(raw) -> str | None:
    if not raw or (isinstance(raw, float) and pd.isna(raw)):
        return None
    return DIFFICULTY_MAP.get(str(raw).strip().lower(), str(raw).strip())


def parse_list(raw) -> list[str]:
    if not raw or (isinstance(raw, float) and pd.isna(raw)):
        return []
    return [s.strip() for s in str(raw).split(",") if s.strip()]


def clear_tables(session):
    print("Clearing games-related tables...")
    session.execute(text("DELETE FROM game_settings"))
    session.execute(text("DELETE FROM game_equipment"))
    session.execute(text("DELETE FROM user_favourites"))
    session.execute(text("DELETE FROM games"))
    session.commit()
    print("Tables cleared.")


def verify_contributor(session) -> str:
    result = session.execute(
        text("SELECT id FROM users WHERE id = :id"),
        {"id": CONTRIBUTOR_ID}
    ).fetchone()
    if not result:
        print(f"ERROR: User {CONTRIBUTOR_ID} not found in DB.")
        sys.exit(1)
    print(f"Contributor verified: {CONTRIBUTOR_ID}")
    return CONTRIBUTOR_ID


EXTRA_GAMES = [
    {
        "id": "fd0af3ae-5cfc-4f99-bee6-a7ff660d0dc0",
        "name": "Chase The Ace",
        "description": "Make sure you don't have the ace by the time the game ends!",
        "age_rating": "All Ages",
        "game_type": "Bluffing",
        "min_players": 2,
        "max_players": 7,
        "duration": "5-10 minutes",
        "difficulty": "Easy",
        "equipment": ["Less Than a Deck of Cards", "Deck of Cards"],
        "game_setting": ["Pub / Bar", "Game Night", "Friendship Ruiner"],
        "objective": "Complete your set of cards or assist others in completing theirs, passing on the ace if you have it.",
        "setup": "1. Determine the number of players.\n2. Lay out the appropriate set of cards based on the number of players (e.g., for 4 players, remove all kings, queens, jacks, 10s, and one ace).\n3. Shuffle the cards you've taken out\n4. Pass the shuffled cards around the players.\n5. The person with 5 cards starts.",
        "rules": "1. Turn to the person next to you and identify the card they need. Pass a card to them face down.\n2. The recipient can choose to accept or reject the card.\n3. The recipient can reject the card up to two times; on the third attempt, they must accept the card.\n4. If possible, help the recipient complete their set by passing the correct card. Alternatively, if you have the ace, try to pass it to them.\n5. If you have completed your own set, you may lay it down, and the game ends.\n6. If you have the ace when another player has completed their set, you lose.",
        "is_public": True,
        "is_whats_that_game_verified": False,
        "contributor_username": "maxswaine",
    },
    {
        "id": "7b75781d-ad49-4add-b41d-8c2fb05db70a",
        "name": "Electric Shoe",
        "description": "Absolutely terrifying and hilarious, this game will have you and your friends laughing and screaming as you try to survive the chaos together",
        "age_rating": "All Ages",
        "game_type": "Physical",
        "min_players": 2,
        "max_players": 20,
        "duration": "Under 5 minutes",
        "difficulty": "Easy",
        "equipment": ["No Equipment"],
        "game_setting": ["Game Night"],
        "objective": "Match each person's shoes to the correct feet.",
        "setup": "1. Ask everyone to take off their shoes and place them into a big pile in the middle of the room.\n2. Have one person leave the room and stay outside until the game begins.\n3. The people inside the room decide which shoe belongs to which person without revealing this to the person outside.\n4. Once the shoes are assigned, invite the person outside to come back into the room.\n5. Ask the outside person to match each person to their shoe.",
        "rules": "1. The game involves an electric shoe that is hidden beneath a pile of shoes. Place the electric shoe under the pile, ensuring there are enough shoes on top to prevent the game from ending too quickly.\n2. The game can only be played once with a specific group of people, so set it up carefully beforehand.\n3. Do not reveal the location of the electric shoe to the person outside the game.\n4. As the person searches for the shoes, encourage and praise their efforts to keep them motivated.\n5. When the electric shoe is found, it will jump unexpectedly, causing excitement and surprise.",
        "is_public": True,
        "is_whats_that_game_verified": False,
        "contributor_username": "test1",
    },
]


def lookup_user_by_username(session, username: str, fallback_id: str) -> str:
    result = session.execute(
        text("SELECT id FROM users WHERE username = :username"),
        {"username": username}
    ).fetchone()
    if result:
        return result[0]
    print(f"  ⚠ User '{username}' not found, using default contributor.")
    return fallback_id


def seed_extra_games(session, fallback_contributor_id: str):
    print(f"\nSeeding {len(EXTRA_GAMES)} extra game(s)...")
    for game in EXTRA_GAMES:
        contributor_id = lookup_user_by_username(session, game["contributor_username"], fallback_contributor_id)

        session.execute(text("""
            INSERT INTO games (
                id, name, description, age_rating, game_type,
                min_players, max_players, duration, difficulty,
                objective, setup, rules,
                image_url, is_public, is_whats_that_game_verified,
                upvotes, contributor_id, created_at
            ) VALUES (
                :id, :name, :description, :age_rating, :game_type,
                :min_players, :max_players, :duration, :difficulty,
                :objective, :setup, :rules,
                NULL, :is_public, :is_verified,
                0, :contributor_id, :created_at
            )
        """), {
            "id": game["id"],
            "name": game["name"],
            "description": game["description"],
            "age_rating": game["age_rating"],
            "game_type": game["game_type"],
            "min_players": game["min_players"],
            "max_players": game["max_players"],
            "duration": game["duration"],
            "difficulty": game["difficulty"],
            "objective": game["objective"],
            "setup": game["setup"],
            "rules": game["rules"],
            "is_public": game["is_public"],
            "is_verified": game["is_whats_that_game_verified"],
            "contributor_id": contributor_id,
            "created_at": datetime.now(timezone.utc),
        })

        for item in game["equipment"]:
            session.execute(text("""
                INSERT INTO game_equipment (id, game_id, equipment_name)
                VALUES (:id, :game_id, :name)
            """), {"id": str(uuid.uuid4()), "game_id": game["id"], "name": item})

        for setting in game["game_setting"]:
            session.execute(text("""
                INSERT INTO game_settings (id, game_id, setting_name)
                VALUES (:id, :game_id, :setting_name)
            """), {"id": str(uuid.uuid4()), "game_id": game["id"], "setting_name": setting})

        print(f"  ✓ {game['name']}")

    session.commit()


def seed(session, contributor_id: str):
    df = pd.read_excel(EXCEL_PATH, sheet_name="Game Submissions", header=1, skiprows=[0])
    df = df.dropna(subset=["Game Name"])

    inserted = 0
    for _, row in df.iterrows():
        game_id = str(uuid.uuid4())

        session.execute(text("""
            INSERT INTO games (
                id, name, description, age_rating, game_type,
                min_players, max_players, duration, difficulty,
                objective, setup, rules,
                image_url, is_public, is_whats_that_game_verified,
                upvotes, contributor_id, created_at
            ) VALUES (
                :id, :name, :description, :age_rating, :game_type,
                :min_players, :max_players, :duration, :difficulty,
                :objective, :setup, :rules,
                NULL, TRUE, TRUE,
                0, :contributor_id, :created_at
            )
        """), {
            "id": game_id,
            "name": str(row["Game Name"]).strip(),
            "description": str(row["Description"]).strip(),
            "age_rating": str(row["Age Rating"]).strip(),
            "game_type": map_game_type(row["Game Type"]),
            "min_players": int(row["Min Players"]),
            "max_players": int(row["Max Players"]),
            "duration": map_duration(row["Duration"]),
            "difficulty": map_difficulty(row.get("Difficulty")),
            "objective": str(row["Objective"]).strip(),
            "setup": str(row["Setup"]).strip(),
            "rules": str(row["Rules"]).strip(),
            "contributor_id": contributor_id,
            "created_at": datetime.now(timezone.utc),
        })

        equipment_items = parse_list(row.get("Equipment")) or ["No Equipment"]
        for item in equipment_items:
            session.execute(text("""
                INSERT INTO game_equipment (id, game_id, equipment_name)
                VALUES (:id, :game_id, :name)
            """), {"id": str(uuid.uuid4()), "game_id": game_id, "name": item})

        for setting in parse_list(row.get("Themes")):
            session.execute(text("""
                INSERT INTO game_settings (id, game_id, setting_name)
                VALUES (:id, :game_id, :setting_name)
            """), {"id": str(uuid.uuid4()), "game_id": game_id, "setting_name": setting})

        print(f"  ✓ {row['Game Name']} ({map_difficulty(row.get('Difficulty'))})")
        inserted += 1

    session.commit()
    print(f"\nDone — {inserted} games inserted.")


if __name__ == "__main__":
    with Session() as session:
        clear_tables(session)
        contributor_id = verify_contributor(session)
        seed(session, contributor_id)
        seed_extra_games(session, contributor_id)
