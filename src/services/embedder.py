import json
import os

import numpy as np
from openai import OpenAI

EMBEDDING_MODEL = "text-embedding-3-small"


def _client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    return OpenAI(api_key=api_key)


def build_game_text(game) -> str:
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
    return ". ".join(parts)


def embed_text(text: str) -> list[float]:
    """Call OpenAI and return the embedding vector."""
    response = _client().embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


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
