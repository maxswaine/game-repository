# src/services/optimiser.py
import os

from openai import OpenAI

from src.models.optimisation_models.optimisation_models import \
    OptimisationResult  # Keep the model, just don't return it directly yet
from src.utils.prompts import PROMPT_TEMPLATES

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class TextOptimiser:
    def __init__(self, field_type: str):
        self.field_type = field_type
        if field_type not in PROMPT_TEMPLATES:
            raise ValueError(f"Unknown field type: {field_type}")

        self.system_instruction = PROMPT_TEMPLATES[field_type]

    def optimise(self, user_text: str) -> OptimisationResult:  # Keeps typed return for IDE safety
        """
        Sends the text to AI and returns both original and optimized versions.
        Note: We still return OptimisationResult here because it's typed and convenient.
        The API layer will handle wrapping it into OptimisationResponse.
        """
        if not user_text or len(user_text.strip()) < 10:
            return OptimisationResult(
                status="success",
                original=user_text,
                optimized=user_text,
                note="Text too short for optimization."
            )

        messages = [
            {"role": "system", "content": self.system_instruction},
            {"role": "user", "content": f"Input: {user_text}"}
        ]

        try:
            response = client.responses.create(
                model="gpt-4.1-nano",
                input=messages,
                temperature=0.2,
            )

            optimized_text = response.output_text

            return OptimisationResult(
                status="success",
                original=user_text.strip(),
                optimized=optimized_text.strip(),
                char_count_saved=len(user_text) - len(optimized_text),
                note=None
            )

        except Exception as e:
            return OptimisationResult(
                status="failed",
                original=user_text,
                optimized=user_text,
                note=f"Optimization failed: {str(e)}"
            )


_optimisers = {}


def get_optimiser(field_type: str):
    if field_type not in _optimisers:
        _optimisers[field_type] = TextOptimiser(field_type)
    return _optimisers[field_type]
