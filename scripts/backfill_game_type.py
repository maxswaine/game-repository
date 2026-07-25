"""
Backfill Game.game_type values that are no longer valid GameTypeEnum members.

Commit 479bffa removed 'Board', 'Logic', 'Puzzle', 'Roleplay', 'Bluffing', 'Improv'
from GameTypeEnum. Existing rows still hold those strings, which now fail Pydantic
validation on read (GameRead), crashing GET /games/ and /games/mine for any game
with an old value.

Usage:
    DATABASE_URL=<railway_url> python scripts/backfill_game_type.py           # dry run
    DATABASE_URL=<railway_url> python scripts/backfill_game_type.py --apply   # writes
"""

import os
import sys
from pathlib import Path

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set.")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.tables import Game
from src.models.enums.game_type_enum import GameTypeEnum

MAPPING = {
    "Board": GameTypeEnum.card.value,
    "Logic": GameTypeEnum.strategy.value,
    "Puzzle": GameTypeEnum.strategy.value,
    "Roleplay": GameTypeEnum.acting.value,
    "Bluffing": GameTypeEnum.strategy.value,
    "Improv": GameTypeEnum.guessing.value,
}

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

apply = "--apply" in sys.argv


def run():
    with Session() as session:
        games = session.query(Game).filter(Game.game_type.in_(MAPPING.keys())).all()

        if not games:
            print("No games with stale game_type values found.")
            return

        print(f"Found {len(games)} game(s) with stale game_type:\n")
        for game in games:
            new_value = MAPPING[game.game_type]
            print(f"  {game.name!r}: {game.game_type!r} -> {new_value!r}")
            if apply:
                game.game_type = new_value

        if apply:
            session.commit()
            print(f"\nUpdated {len(games)} game(s).")
        else:
            print("\nDry run only — rerun with --apply to write changes.")


if __name__ == "__main__":
    run()
