"""
Generate and store embeddings for all games in the database.

Run this once after seeding, and again whenever new games are added.

Usage:
    DATABASE_URL=<railway_url> OPENAI_API_KEY=<key> python scripts/embed_games.py

    # Force re-embed all games (including those already embedded):
    DATABASE_URL=<url> OPENAI_API_KEY=<key> python scripts/embed_games.py --force
"""

import os
import sys
import time
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

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, joinedload

DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set.")
    sys.exit(1)

if not OPENAI_API_KEY:
    print("ERROR: OPENAI_API_KEY not set.")
    sys.exit(1)

# Add project root to path so src imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.tables import Game
from src.services.embedder import build_game_text, embed_text, embedding_to_json

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

force = "--force" in sys.argv


def run():
    with Session() as session:
        query = session.query(Game).options(
            joinedload(Game.setting_items),
            joinedload(Game.equipment_items),
        )
        if not force:
            query = query.filter(Game.embedding.is_(None))

        games = query.all()

        if not games:
            print("All games already embedded. Use --force to re-embed.")
            return

        print(f"Embedding {len(games)} game(s)...")
        embedded = 0
        failed = 0

        for game in games:
            text = build_game_text(game)
            try:
                vector = embed_text(text)
                game.embedding = embedding_to_json(vector)
                session.commit()
                print(f"  ✓ {game.name}")
                embedded += 1
                # Small pause to be kind to rate limits
                time.sleep(0.1)
            except Exception as e:
                print(f"  ✗ {game.name}: {e}")
                session.rollback()
                failed += 1

        print(f"\nDone — {embedded} embedded, {failed} failed.")


if __name__ == "__main__":
    run()
