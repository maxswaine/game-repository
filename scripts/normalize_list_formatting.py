"""
Normalize numbered/bulleted list formatting in game text fields (setup, rules,
objective, description) so consecutive list items are always separated by a
blank line (\\n\\n). Leaves everything else (marker style, numbering, intro
text) untouched.

Usage:
    DATABASE_URL=<url> python scripts/normalize_list_formatting.py            # dry run, prints diffs
    DATABASE_URL=<url> python scripts/normalize_list_formatting.py --apply    # writes changes
"""

import os
import re
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

# Only matches markers at column 0 (top-level items) so indented sub-bullets
# under a list item are left untouched rather than being split out and
# flattened to the same level.
MARKER_RE = re.compile(r"^([0-9]+\.|[-*])[ \t]+", re.MULTILINE)
FIELDS = ["objective", "setup", "rules", "description"]


def normalize(text: str) -> str:
    if not text:
        return text

    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)

    matches = list(MARKER_RE.finditer(text))
    if len(matches) < 2:
        return text

    prefix = text[: matches[0].start()].rstrip()
    pieces = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        piece = text[m.start():end].rstrip()
        pieces.append(piece)

    result = (prefix + "\n\n" if prefix else "") + "\n\n".join(pieces)
    return result


def main():
    apply = "--apply" in sys.argv

    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    games = session.query(Game).all()
    changed = 0

    for game in games:
        updates = {}
        for field in FIELDS:
            original = getattr(game, field)
            fixed = normalize(original)
            if fixed != original:
                updates[field] = (original, fixed)

        if not updates:
            continue

        changed += 1
        print(f"\n=== {game.name} ({game.id}) ===")
        for field, (original, fixed) in updates.items():
            print(f"--- {field} (before) ---")
            print(original)
            print(f"--- {field} (after) ---")
            print(fixed)
            if apply:
                setattr(game, field, fixed)

    if apply:
        session.commit()
        print(f"\nApplied fixes to {changed} games.")
    else:
        print(f"\nDry run: {changed} games would be changed. Re-run with --apply to write changes.")

    session.close()


if __name__ == "__main__":
    main()
