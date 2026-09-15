import json
import logging
import os

from openai import OpenAI

from src.models.optimisation_models.brain_dump_models import BrainDumpResult
from src.utils.prompts import BRAIN_DUMP_PROMPT, REJECTION_SENTINEL

logger = logging.getLogger(__name__)

MIN_DUMP_LENGTH = 20
FIELDS = ("objective", "setup", "rules")

_SCHEMA = {
    "type": "object",
    "properties": {
        "objective": {"type": "string"},
        "setup": {"type": "string"},
        "rules": {"type": "string"},
    },
    "required": ["objective", "setup", "rules"],
    "additionalProperties": False,
}


def _get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    return OpenAI(api_key=api_key)


class BrainDumpSplitter:
    def split(self, dump_text: str) -> tuple[BrainDumpResult | None, list[str], str | None]:
        messages = [
            {"role": "system", "content": BRAIN_DUMP_PROMPT},
            {"role": "user", "content": f"<user_submitted_text>\n{dump_text}\n</user_submitted_text>"},
        ]
        try:
            response = _get_client().responses.create(
                model="gpt-4.1-mini",
                input=messages,
                temperature=0.2,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "brain_dump_split",
                        "schema": _SCHEMA,
                        "strict": True,
                    }
                },
            )
            parsed = json.loads(response.output_text)

            if REJECTION_SENTINEL in (parsed.get(f, "") for f in FIELDS):
                logger.warning("Brain dump rejected non-game input: %r", dump_text[:200])
                return None, [], (
                    "This text doesn't look like game content and couldn't be processed. "
                    "Please describe your game in plain language."
                )

            result = BrainDumpResult(
                objective=(parsed.get("objective") or "").strip(),
                setup=(parsed.get("setup") or "").strip(),
                rules=(parsed.get("rules") or "").strip(),
            )
            missing = [field for field in FIELDS if not getattr(result, field)]
            return result, missing, None
        except Exception:
            return None, [], "Brain dump failed, please enter fields manually."


_splitter: BrainDumpSplitter | None = None


def get_brain_dump_splitter() -> BrainDumpSplitter:
    global _splitter
    if _splitter is None:
        _splitter = BrainDumpSplitter()
    return _splitter
