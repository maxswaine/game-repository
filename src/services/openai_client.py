import os
from functools import lru_cache

from openai import OpenAI


@lru_cache(maxsize=1)
def get_openai_client() -> OpenAI:
    """
    Shared OpenAI client.

    Cached so every caller reuses one connection pool. Building a fresh
    ``OpenAI()`` per request means a new TLS handshake to api.openai.com each
    time, which was the bulk of the latency spread on /games/search/.

    ``lru_cache`` does not cache exceptions, so a missing key still raises on
    every call rather than being remembered as a failure.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    return OpenAI(api_key=api_key)
