# In-app Translation — Frontend Integration

## Overview

Translate game text — rules, setup, objective — into another language on demand. Text in, language code in, translated text out.

Backend half is built on branch `feature/translation` (`src/api/translation.py`, `src/services/translator.py`, `src/utils/prompts.py`). **Not pushed, not merged, not deployed.** No migration needed — new endpoints only.

## Provider: OpenAI, not Google Cloud Translation

The original ticket specced Google Cloud Translation v2. It's `gpt-4.1` instead:

- **Accuracy** (the deciding factor). Google's NMT translates sentence-by-sentence, so it drifts game-specific terminology across a rules block — "the pile", "the dealer" come out differently in different sentences, and cross-sentence references break. One model call sees the whole block and is instructed to keep terms consistent and preserve list structure.
- **Cost.** ~$3.30 per 1M source chars vs Google's $20. Roughly 6x cheaper.
- **No new infrastructure.** `openai` is already a dependency with a key already in Railway. Google needs a new GCP project and key.

Where Google would still win: it never invents content, and it covers 135+ languages properly. Revisit if low-resource languages start mattering.

## `POST /translate/`

Auth required.

```ts
// request
{ text: string, target_language: string }   // ISO 639-1, 2 chars, e.g. "es"

// response
{
  success: boolean,
  data: {
    translated_text: string,
    target_language: string,       // always lower-cased
    target_language_name: string   // e.g. "Spanish"
  } | null,
  error_message: string | null
}
```

| Case | Response |
|---|---|
| Success | `200`, `success: true` |
| Model/upstream failure | **`200`, `success: false`** with `error_message` |
| `text` empty or > 8000 chars | `422` |
| `target_language` not a valid ISO 639-1 code | `422` |

**An upstream failure is a 200, not an error status** — same contract as `/optimise/`. Don't treat non-200 as the only failure path.

`target_language` is case-insensitive inbound and always lower-case outbound.

## `GET /metadata/languages`

Open, no auth.

```json
{ "languages": [ { "code": "es", "name": "Spanish" }, ... ] }
```

184 ISO 639-1 languages, sorted by name. Shape is identical to `/metadata/countries`, so it mirrors the existing `fetchCountries()` helper exactly.

Validated against `pycountry` rather than a hand-written enum — a closed set, so `target_language` can't be used to inject into the system prompt, without capping the language list.

## Frontend notes

- **Translate per field, not concatenated.** Rules + setup + objective joined can exceed the 8000-char cap and 422. Separate calls are also smaller and faster.
- **Cache the result.** No server-side cache — every call is a fresh billed model call. `@tanstack/react-query` is already set up with an async-storage persister; key on `[gameId, field, languageCode]` with an effectively infinite stale time, since a translation never changes for a given input.
- **Keep the original.** Don't overwrite source text in state. Show a "translated" affordance and a way back — users need to know it's machine output.
- **Don't render a 184-row picker.** Shortlist first (device locale plus majors), full list behind a search.
- **Quality tails off below the top languages.** All 184 codes validate, but roughly 40–50 are genuinely strong and ~90 usable. Don't advertise "184 languages" as if they're equal.

## Compatibility

Purely new endpoints, nothing existing changed. **No `COMPATIBILITY.md` row needed.** Deploy the backend before the app build that calls `/translate/` goes live.

Trello: [#26](https://trello.com/c/ejPDB8aa)
