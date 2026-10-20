import json
from functools import lru_cache
from types import SimpleNamespace

import numpy as np
from openai import OpenAI

from src.services.openai_client import get_openai_client

EMBEDDING_MODEL = "text-embedding-3-small"


def _client() -> OpenAI:
    return get_openai_client()


def build_game_text(game, aliases: list[str] | None = None) -> str:
    """
    Combine game fields into a single descriptive string for embedding.
    The richer this text, the better the semantic matches.
    """
    parts = [
        game.name,
        game.description,
        f"Type: {game.game_type}",
        f"Players: {game.min_players}-{game.max_players}",
        f"Duration: {game.duration}",
    ]
    if game.setting_items:
        settings = ", ".join(s.setting_name for s in game.setting_items)
        parts.append(f"Settings: {settings}")
    if hasattr(game, "difficulty") and game.difficulty:
        parts.append(f"Difficulty: {game.difficulty}")
    if game.equipment_items:
        equipment = ", ".join(e.equipment_name for e in game.equipment_items)
        parts.append(f"Equipment: {equipment}")
    parts.append(game.objective)
    if game.setup:
        parts.append(f"Setup: {game.setup}")
    if game.rules:
        parts.append(f"Rules: {game.rules}")
    if aliases:
        parts.append(f"Also known as: {', '.join(aliases)}")
    return ". ".join(parts)


def embed_text(text: str) -> list[float]:
    """Call OpenAI and return the embedding vector."""
    response = _client().embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


@lru_cache(maxsize=256)
def _embed_query_cached(text: str) -> np.ndarray:
    """
    Held as a read-only float32 array rather than a list of Python floats:
    ~6KB per entry instead of ~49KB, so a full cache costs ~1.5MB.
    """
    vector = np.asarray(embed_text(text), dtype=np.float32)
    vector.flags.writeable = False
    return vector


def embed_query(text: str) -> np.ndarray:
    """
    Embed a search query, reusing the result for repeats.

    Search queries recur heavily ("party games", "no equipment"), and every
    miss is a network round trip to OpenAI. Game embeddings deliberately do
    not go through here - each game's text is unique, so caching them would
    only consume memory.
    """
    return _embed_query_cached(text)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    dot = np.dot(va, vb)
    norm = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(dot / norm) if norm > 0 else 0.0


def embedding_to_json(vector: list[float]) -> str:
    return json.dumps(vector)


def json_to_embedding(text: str) -> list[float]:
    return json.loads(text)


def build_game_text_from_create(game) -> str:
    """Build embedding text from a GameCreate Pydantic model.

    Delegates to build_game_text rather than rebuilding the string, so the text the duplicate
    check embeds is byte-identical to the text that will be stored for the same game. The two
    had drifted apart: this one dropped the "No Equipment" sentinel and ignored aliases, while
    build_game_text kept both — so every cosine score the duplicate check produced was measured
    against slightly differently-shaped text than the corpus it compared to.
    """
    def value_of(v):
        return v.value if hasattr(v, "value") else str(v)

    shim = SimpleNamespace(
        name=game.name,
        description=game.description,
        game_type=value_of(game.game_type),
        min_players=game.player_count.min_players,
        max_players=game.player_count.max_players,
        duration=value_of(game.duration),
        difficulty=value_of(game.difficulty) if game.difficulty else None,
        setting_items=[
            SimpleNamespace(setting_name=value_of(s)) for s in (game.game_setting or [])
        ],
        equipment_items=[
            SimpleNamespace(equipment_name=value_of(e)) for e in (game.equipment or [])
        ],
        objective=game.objective,
        setup=game.setup,
        rules=game.rules,
    )
    aliases = [a.strip() for a in (getattr(game, "aliases", None) or []) if a.strip()]
    return build_game_text(shim, aliases=aliases)
