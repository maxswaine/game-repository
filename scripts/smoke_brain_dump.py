"""Live smoke test for the Brain Dump OpenAI integration.

Bypasses BrainDumpSplitter.split()'s try/except so any bad request shape or
parse failure is raised loudly instead of being swallowed into the graceful
fallback string. Run with a real OPENAI_API_KEY loaded.

    python scripts/smoke_brain_dump.py

Expected: prints a BrainDumpResult with populated fields (not an error).
Cost: ~$0.001.
"""
import json

from dotenv import load_dotenv

load_dotenv()

from src.services.brain_dump import _get_client, _SCHEMA
from src.utils.prompts import BRAIN_DUMP_PROMPT

DUMP = (
    "You roll dice and race to empty your hand of cards. Deal seven cards each "
    "to start. On your turn play a matching card or draw one."
)

messages = [
    {"role": "system", "content": BRAIN_DUMP_PROMPT},
    {"role": "user", "content": f"Input: {DUMP}"},
]

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

print("RAW output_text:", response.output_text)
parsed = json.loads(response.output_text)
print("PARSED:", json.dumps(parsed, indent=2))
assert set(parsed) == {"objective", "setup", "rules"}, "unexpected keys"
assert parsed["objective"] and parsed["rules"], "fields came back empty — extraction failed"
print("\nSMOKE PASS — structured output shape accepted and fields populated.")
