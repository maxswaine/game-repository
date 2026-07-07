# Focus Group Feedback — Backend Tasks
**Date:** 07/07/2026 | **Retest deadline:** 10/07/2026 (Thursday)

---

## Thursday Priority

### 1. Logout bug — refresh endpoint investigation
**Symptom:** Users get logged out when backgrounding the app. The frontend `AuthContext` listens to `auth:logout` which fires when `POST /auth/refresh` returns a non-200.

**Tasks:**
- Pull Railway logs from the focus group session (07/07/2026, ~afternoon) and find all `POST /auth/refresh` calls that returned non-200
- Identify whether the refresh endpoint is rejecting valid refresh tokens on app resume (e.g. cookie not sent, short token TTL, missing header)
- If the refresh token is valid but the request is malformed on resume, return `401` with a body that distinguishes "token expired" from "bad request" — the frontend can use this to decide whether to prompt re-login vs silently retry
- Ensure refresh token TTL is long enough for reasonable session gaps (backgrounding for minutes, not days)

---

## Backend Concerns (post-Thursday)

### 2. 500 error on Add Game submission
**Symptom:** Live in session — users got a 500 when trying to submit a game. This blocks a core contribution flow.

**Tasks:**
- Pull Railway logs for `POST /games` (or equivalent) around the session timestamp
- Identify the unhandled exception — likely a missing required field, schema validation gap, or DB constraint violation
- Replace the 500 with a `422 Unprocessable Entity` with a descriptive error body
- Add input validation at the handler layer for all required fields before hitting the DB
- Write a regression test for the failing case

---

### 3. AI search prompt doesn't handle time/duration intent
**Symptom:** Harry asked for a "1 hour" game — the AI search returned irrelevant results. The prompt likely passes the raw user query without extracting structured filters.

**Tasks:**
- Update the system prompt for the AI search endpoint to explicitly extract duration intent from natural language:
  - e.g. "1 hour", "quick game", "short", "all evening" → map to the `duration` filter field values
  - e.g. "for 4 people", "just me and a friend" → map to `player_count`
  - e.g. "drinking game", "card game" → map to `game_type`
- Return a structured filter object from the LLM extraction step, then apply those filters to the standard game query — do not return raw LLM-generated game descriptions
- Add a fallback: if extraction confidence is low, surface the manual filters to the user instead of returning empty/wrong results
- Log queries + extracted filters for future prompt tuning

---

### 4. Rules missing edge cases and jargon definitions
**Symptom:** Harry (Chase the Ace) couldn't follow edge cases. Jargon in rules went unexplained. Users said bad rules on two games would make them leave the app permanently.

**Tasks:**

**Schema changes:**
- Add optional `edge_cases` field to the game schema: array of `{ situation: string, ruling: string }`
- Add optional `glossary` field: array of `{ term: string, definition: string }`
- Expose both in the game detail API response

**Content:**
- Audit the top 20 most-viewed games for missing edge cases and undefined jargon
- Update rules for Chase the Ace and Electric Shoe as immediate fixes (both called out in session)

**AI-assisted rule generation (if applicable):**
- If rules are generated or assisted by LLM, extend the prompt to explicitly require:
  - At least 3 edge cases for games with 4+ rules
  - Definitions for any domain-specific terms used

---

## Context — What Frontend Expects

The frontend (`GameDetailScreen.tsx`) will surface `edge_cases` and `glossary` as expandable sections once the schema is updated. Coordinate on field names before shipping the schema change so both sides can deploy together.

The frontend will also surface a "Verified" badge more prominently — ensure the `is_verified` flag is present and accurate on all game detail responses.

---

## Roadmap (validated but not scheduled)

| Feature | Notes |
|---|---|
| Profile picture upload | S3 upload endpoint + user profile `avatar_url` field |
| Interactive / step-through rules | Structured `steps[]` schema with optional `practice_round` flag |
| Speech-to-rules (brain dump) | STT → structured rule extraction endpoint |
| Friends / social graph | Follow model, shared wishlist visibility |
| Ads | Age-gate logic based on user profile `age` or `age_verified` |
