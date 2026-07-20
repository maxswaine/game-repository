# Brain Dump — Design Spec

**Date:** 2026-07-20
**Branch:** `feature/pre-launch-features`
**Status:** Approved design, pre-implementation

## Purpose

When creating a game, a user can press a single **Brain Dump** button, type or dictate
one freeform blob describing the game, and have the backend split it into the three core
gameplay text fields — `objective`, `setup`, `rules`. The frontend pre-fills the
create-game form with the result; the user reviews and edits; then the normal
`POST /games/` flow saves the game.

This removes the friction of filling three separate structured fields by hand during
setup, while keeping the user in full control of the final content.

## Scope

**In scope**
- One new authenticated endpoint that accepts freeform text and returns a split draft.
- Splitting into exactly `objective`, `setup`, `rules` (text fields only).
- Best-effort extraction: fields not described in the dump come back empty, never invented.
- Reporting which fields came back empty so the frontend can nudge the user.

**Out of scope (YAGNI)**
- Structured metadata extraction (players, duration, difficulty, game_type, equipment) —
  user fills these via existing pickers. Deferred; may revisit post-launch.
- `description` field — user writes the short pitch separately.
- Server-side audio transcription — speech-to-text is client-side/native; the backend
  only ever receives text.
- Persisting anything — Brain Dump returns a draft only. No game row is created until the
  user submits the normal create-game form.
- A `leftover` / unclassified-text bucket — deferred to v2 if extraction feels lossy.

## Architecture

Brain Dump reuses the existing optimiser plumbing (`src/services/optimiser.py`,
`src/api/optimisation.py`, `src/utils/prompts.py`, `src/services/moderation.py`). It is a
stateless, single-shot OpenAI call — no OpenAI Assistant/agent, no persistence.

### Endpoint

```
POST /optimise/brain-dump      (auth required — same dependency as POST /optimise/)
```

Registered in the existing optimisation router (`src/api/optimisation.py`), mounted at
`/optimise` in `src/main.py`.

**Request body** (`BrainDumpRequest`):
```json
{ "dump_text": "you roll dice and try to get rid of all your cards first ..." }
```

**Response body** (`BrainDumpResponse`):
```json
{
  "success": true,
  "data": {
    "objective": "Be the first player to get rid of all your cards.",
    "setup": "",
    "rules": "On your turn, roll the dice and play a matching card ..."
  },
  "missing_fields": ["setup"],
  "error_message": null
}
```

- `success: bool` — whether extraction ran successfully.
- `data: BrainDumpResult | null` — the three split fields; `null` when `success` is false.
  - `objective: str`, `setup: str`, `rules: str` — empty string `""` when the dump did not
    describe that field.
- `missing_fields: list[str]` — subset of `["objective", "setup", "rules"]` that came back
  empty. Empty list when all three were populated.
- `error_message: str | null` — human-readable reason when `success` is false (too short,
  moderation, upstream failure).

### Service

New `BrainDumpSplitter` (in `src/services/optimiser.py` alongside `TextOptimiser`, or a
sibling module `src/services/brain_dump.py` — implementer's call, follow existing style).

- **Model:** `gpt-4.1-mini` (not nano). Better judgment on the setup-vs-rules boundary and
  stronger adherence to "do not invent". Cost is ~$0.001/call — negligible.
- **Structured output:** use OpenAI JSON-schema structured outputs so the response is
  guaranteed to be valid JSON with exactly the keys `objective`, `setup`, `rules` (each a
  string). This eliminates any malformed-JSON parse-failure path.
- **Temperature:** 0.2 — low, to suppress creative padding.
- **System prompt:** new template in `src/utils/prompts.py`. Must instruct:
  - Split the input into `objective`, `setup`, and `rules`.
  - Use ONLY information present in the input.
  - If a field is not described, return an empty string for it — never invent objectives,
    setup steps, or rules.
  - Do not merge unrelated content into a field to avoid leaving it empty.

After the call, the service computes `missing_fields` by checking which of the three
returned strings are empty/whitespace.

### Guardrails

1. **Min length:** `dump_text` shorter than 20 characters (after strip) → `success=false`,
   `error_message="Text too short to split."`, no OpenAI call.
2. **Max length:** cap `dump_text` at 4000 characters → 422 (or truncate + note; prefer
   422 for predictability). Bounds token cost.
3. **Moderation:** run `check_content(dump_text)` (same as `/optimise/`). Violation → 422
   `"Content violates community guidelines."`.
4. **Upstream failure:** any OpenAI exception → `success=false`,
   `error_message="Brain dump failed, please enter fields manually."`, `data=null`. The
   game-creation flow is never blocked — the user can always fill fields by hand.

### Models (Pydantic)

New module `src/models/optimisation_models/brain_dump_models.py` (or extend the existing
optimisation models module):

- `BrainDumpRequest` — `dump_text: str`
- `BrainDumpResult` — `objective: str`, `setup: str`, `rules: str`
- `BrainDumpResponse` — `success: bool`, `data: BrainDumpResult | None`,
  `missing_fields: list[str]`, `error_message: str | None`

## Frontend Integration

**Trigger:** a "Brain Dump" button in the create-game / rule-setup flow. Tapping it opens a
textarea. Native/client-side speech-to-text feeds text into the textarea (backend receives
text only — no audio upload).

**Call:** `POST /optimise/brain-dump` with `{ "dump_text": <textarea contents> }`, bearer
token / auth cookie (auth required).

**On `success: true`:**
- Pre-fill the form's `objective`, `setup`, `rules` fields from `data`.
- The user can freely edit every field afterward — the draft is a starting point, not final.
- For each field name in `missing_fields`, show an inline hint, e.g. *"We couldn't find
  setup steps — add them below."* Do not block submission on missing fields.

**On `success: false`:**
- Keep the user in manual entry. Show `error_message` as a non-blocking notice.
- Never lose the user's original dump text — leave it in the textarea so they can retry or
  copy from it.

**Errors:**
- `422` — validation/moderation failure. Surface `detail` from the response; keep manual
  entry available.
- `401` — auth required (user must be logged in to create a game anyway).

**Important:** Brain Dump never creates or modifies a game. The game is only persisted when
the user submits the existing `POST /games/` form. Nothing about the existing create flow
changes except that three fields may arrive pre-filled.

## Testing

Unit/integration tests (mock the OpenAI call — no live API in tests):

- Happy path: well-formed dump → all three fields populated, `missing_fields == []`,
  `success=true`.
- Partial dump: dump with no setup info → `setup == ""`, `missing_fields == ["setup"]`.
- Too short: `dump_text` under 20 chars → `success=false`, correct `error_message`, no
  OpenAI call made (assert the client is not invoked).
- Moderation reject: `check_content` returns false → 422.
- Max length: over 4000 chars → 422.
- Upstream failure: OpenAI client raises → `success=false`, `data=null`, fallback
  `error_message`.
- Auth: unauthenticated request → 401.

Follow the existing test setup (SQLite `test.db`, `client_with_auth`). Mock OpenAI the same
way existing optimiser tests do (or introduce a mock if none exists).

## Cost

Per `docs/ai-photo-cost-analysis.md`: one `gpt-4.1-mini` call, ~860 tokens in / ~400 out ≈
**~$0.001/call**. At 10k games/month ≈ **~$10/month** — negligible against the ~$9–20/month
platform baseline. No prompt caching (prompt < 1024-token cache threshold) and no Assistant
API — stateless resend is cheapest and simplest at this size.

## Open questions / future work

- If extraction proves lossy, add a `leftover` field in v2 so ambiguous sentences have a
  home instead of being force-fit or dropped.
- Structured-metadata extraction (players/duration/difficulty) is a natural v2 extension
  once the text-split path is proven.
