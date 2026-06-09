import logging
import os

from openai import OpenAI

logger = logging.getLogger(__name__)


def check_content(text: str) -> bool:
    """Returns True if content is safe to store, False if it should be blocked."""
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.moderations.create(
            model="omni-moderation-2024-09-26",
            input=text,
        )
        result = response.results[0]
        return not (result.categories.hate or result.categories.hate_threatening)
    except Exception as e:
        logger.error("Moderation API error: %s", e)
        return True
