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
    "casual":               "Card",
    "casual / prediction":  "Card",
    "casual / cards":       "Card",
    "casual / thinking":    "Word",
    "casual / coin":        "Other",
    "bluff / strategy":     "Bluffing",
    "bluff / cards":        "Bluffing",
    "party / drawing":      "Drawing",
    "reflex / cards":       "Card",
    "skill / coin":         "Physical",
    "speaking / word":      "Word",
    "speaking / guessing":  "Guessing",
    "social / speaking":    "Improv",
}

DURATION_MAP = {
    "under 5 minutes":   "Under 5 minutes",
    "5-10 minutes":      "5-10 minutes",
    "10-15 minutes":     "10-15 minutes",
    "15-30 minutes":     "15-30 minutes",
    "30-45 minutes":     "30-45 minutes",
    "45-60 minutes":     "45-60 minutes",
    "1-2 hours":         "1-2 hours",
}

DIFFICULTY_MAP = {
    "easy":   "Easy",
    "medium": "Medium",
    "hard":   "Hard",
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

        for item in parse_list(row.get("Equipment")):
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
