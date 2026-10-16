from unittest.mock import patch

import numpy as np
import pytest

from src.services import embedder
from src.services.openai_client import get_openai_client


@pytest.fixture(autouse=True)
def _clear_caches():
    """Both caches are module-level, so they would otherwise leak between tests."""
    get_openai_client.cache_clear()
    embedder._embed_query_cached.cache_clear()
    yield
    get_openai_client.cache_clear()
    embedder._embed_query_cached.cache_clear()


def test_client_is_reused_across_calls(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assert get_openai_client() is get_openai_client()


def test_missing_key_raises_every_time(monkeypatch):
    """lru_cache must not memoise the failure - a key set later should work."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        get_openai_client()
    with pytest.raises(ValueError):
        get_openai_client()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assert get_openai_client() is not None


def test_embed_query_caches_repeats():
    vector = [0.1] * 1536
    with patch.object(embedder, "embed_text", return_value=vector) as spy:
        first = embedder.embed_query("party games")
        second = embedder.embed_query("party games")

    assert spy.call_count == 1
    assert np.array_equal(first, second)


def test_embed_query_distinguishes_different_queries():
    with patch.object(embedder, "embed_text", return_value=[0.1] * 1536) as spy:
        embedder.embed_query("party games")
        embedder.embed_query("no equipment")

    assert spy.call_count == 2


def test_cached_vector_cannot_be_mutated_by_callers():
    """A caller mutating the returned array would corrupt every later hit."""
    with patch.object(embedder, "embed_text", return_value=[0.1] * 1536):
        vector = embedder.embed_query("party games")

    with pytest.raises(ValueError):
        vector[0] = 99.0
