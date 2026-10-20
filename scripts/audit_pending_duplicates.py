"""Re-run the duplicate check over everything currently in the review queue.

Answers two questions the live API cannot answer after the fact:

  1. Which pending games are duplicates of something already approved?
  2. Would a stronger judge model have caught the ones nano missed?

It imports the production functions (build_game_text, embed_text, cosine_similarity,
judge_potential_duplicate), so what it reports is what the real check would decide — not an
approximation. Embeddings are recomputed here rather than read from the DB, so no database
access or DATABASE_URL is needed; at ~140 games that is a fraction of a cent.

Usage:
    OPENAI_API_KEY=sk-... ADMIN_TOKEN=eyJ... \
        SECRET_KEY=x DATABASE_URL=sqlite:///./tmp.db \
        PYTHONPATH=. python scripts/audit_pending_duplicates.py [model ...]

    Models default to the nano/mini/4.1 ladder. Pass names to override, e.g.
        ... python scripts/audit_pending_duplicates.py gpt-4.1-nano gpt-4.1

ADMIN_TOKEN needs role=admin (it reads /admin/games/pending). Read-only: nothing is written
to the API or the database.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from types import SimpleNamespace

from src.services.duplicate_judge import judge_potential_duplicate
from src.services.embedder import build_game_text, cosine_similarity, embed_text
from src.utils.config import DUPLICATE_CANDIDATE_THRESHOLD, DUPLICATE_SIMILARITY_THRESHOLD

API = os.getenv("API_BASE", "https://api.whatsthatgame.co.uk")
DEFAULT_MODELS = ["gpt-4.1-nano", "gpt-4.1-mini", "gpt-4.1"]


def _get(path: str, token: str | None = None) -> list[dict]:
    req = urllib.request.Request(
        f"{API}{path}",
        headers={
            "Authorization": f"Bearer {token}" if token else "",
            # The edge rejects urllib's default agent.
            "User-Agent": "wtg-duplicate-audit",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        sys.exit(f"GET {path} failed: {e.code} {e.read()[:200]!r}")


def _as_row(game: dict) -> SimpleNamespace:
    """A GameRead payload shaped the way build_game_text reads a Game row."""
    return SimpleNamespace(
        name=game["name"],
        description=game["description"],
        game_type=game["game_type"],
        min_players=game["player_count"]["min_players"],
        max_players=game["player_count"]["max_players"],
        duration=game["duration"],
        difficulty=game.get("difficulty"),
        setting_items=[
            SimpleNamespace(setting_name=s) for s in (game.get("game_setting") or [])
        ],
        equipment_items=[
            SimpleNamespace(equipment_name=e) for e in (game.get("equipment") or [])
        ],
        objective=game["objective"],
        setup=game["setup"],
        rules=game["rules"],
    )


def _text(game: dict) -> str:
    return build_game_text(_as_row(game), aliases=game.get("aliases") or [])


def main() -> None:
    token = os.getenv("ADMIN_TOKEN")
    if not token:
        sys.exit("ADMIN_TOKEN is required (an admin bearer token).")
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is required.")
    models = sys.argv[1:] or DEFAULT_MODELS

    pending = _get("/admin/games/pending", token)
    approved = []
    offset = 0
    while True:
        page = _get(f"/games/?limit=200&offset={offset}", token)
        approved += page
        if len(page) < 200:
            break
        offset += 200

    print(f"{len(pending)} pending, {len(approved)} approved, judges: {', '.join(models)}")
    print(
        f"thresholds: candidate >= {DUPLICATE_CANDIDATE_THRESHOLD}, "
        f"auto-flag >= {DUPLICATE_SIMILARITY_THRESHOLD}\n"
    )

    print("embedding the approved catalogue...", end=" ", flush=True)
    approved_vectors = [(g, embed_text(_text(g))) for g in approved]
    print("done\n")

    verdicts: dict[str, list[str]] = {}
    for game in pending:
        submission_text = _text(game)
        candidate = embed_text(submission_text)
        scored = sorted(
            (
                (round(cosine_similarity(candidate, vector), 4), other)
                for other, vector in approved_vectors
            ),
            key=lambda row: row[0],
            reverse=True,
        )
        print(f"=== {game['name']}  (submitted {game['created_at'][:16]})")

        auto = [(s, g) for s, g in scored if s >= DUPLICATE_SIMILARITY_THRESHOLD]
        gray = [
            (s, g)
            for s, g in scored
            if DUPLICATE_CANDIDATE_THRESHOLD <= s < DUPLICATE_SIMILARITY_THRESHOLD
        ]

        for score, other in auto:
            print(f"    AUTO-FLAG  {score:.4f}  {other['name']}")
            verdicts.setdefault(game["name"], []).append(f"cosine:{other['name']}")

        if not auto and not gray:
            print(f"    no candidates (best: {scored[0][0]:.4f} {scored[0][1]['name']})")

        # The live check only judges the gray zone, and only when nothing auto-flagged.
        for score, other in gray[:5] if not auto else []:
            row = [f"    gray {score:.4f}  {other['name']:28}"]
            for model in models:
                try:
                    same = judge_potential_duplicate(submission_text, _text(other), model=model)
                    row.append(f"{model}={'YES' if same else 'no '}")
                    if same:
                        verdicts.setdefault(game["name"], []).append(f"{model}:{other['name']}")
                except Exception as e:
                    row.append(f"{model}=ERR({type(e).__name__})")
            print("  ".join(row))
        print()

    print("--- summary ---")
    for game in pending:
        hits = verdicts.get(game["name"])
        print(f"  {game['name']:28} {'DUPLICATE of ' + ', '.join(hits) if hits else 'clean'}")


if __name__ == "__main__":
    main()
