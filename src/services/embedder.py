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
    """Build embedding text from a GameCreate Pydantic model."""
    parts = [
        game.name,
        game.description,
        f"Type: {game.game_type.value if hasattr(game.game_type, 'value') else game.game_type}",
        f"Players: {game.player_count.min_players}-{game.player_count.max_players}",
        f"Duration: {game.duration}",
    ]
    if game.game_setting:
        settings = ", ".join(
            s.value if hasattr(s, "value") else str(s) for s in game.game_setting
        )
        parts.append(f"Settings: {settings}")
    if game.difficulty:
        diff = game.difficulty.value if hasattr(game.difficulty, "value") else game.difficulty
        parts.append(f"Difficulty: {diff}")
    if game.equipment:
        equipment = [
            e.value if hasattr(e, "value") else str(e)
            for e in game.equipment
            if (e.value if hasattr(e, "value") else str(e)) != "No Equipment"
        ]
        if equipment:
            parts.append(f"Equipment: {', '.join(equipment)}")
    parts.append(game.objective)
    return ". ".join(parts)


def find_similar_games(
    games: list,
    candidate_embedding: list[float],
    threshold: float,
) -> list[tuple]:
    """Return (game, score) pairs where cosine similarity >= threshold, sorted descending."""
    results = []
    for game in games:
        if not game.embedding:
            continue
        stored = json_to_embedding(game.embedding)
        score = cosine_similarity(candidate_embedding, stored)
        if score >= threshold:
            results.append((game, round(score, 4)))
    return sorted(results, key=lambda x: x[1], reverse=True)
