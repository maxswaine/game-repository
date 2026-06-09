# Frontend API Changes — pre-release-hardening branch

This document covers every API behaviour change that the frontend must handle before this branch
ships. Each section lists the endpoint, what changed, and what the frontend needs to do.

Use `graphify query "<endpoint or feature>"` in the frontend repo to locate which services,
hooks, or components make each call.

---

## 1. Rate limiting — new 429 responses

**Endpoints affected:**
- `POST /auth/token`
- `POST /users/register/`

**Change:** Requests are now rate-limited per IP. Exceeding the limit returns:

```
HTTP 429 Too Many Requests
{"error": "Rate limit exceeded: ..."}
```

Limits: 5 req/min on login, 3 req/min on register.

**Frontend action required:**
- Handle 429 on login and register forms.
- Show a user-friendly message: e.g. "Too many attempts — please wait a moment and try again."
- Do not retry automatically on 429.

---

## 2. `DELETE /users/{user_id}` — status code changed

**Change:** Was `204 No Content` (no body). Now `200 OK` with a JSON body.

```json
{"message": "User account deleted successfully"}
```

**Frontend action required:**
- If any code checked `response.status === 204` to confirm deletion, update it to accept `200`.

---

## 3. `avatar_url` validation — new 422 on unsafe URLs

**Endpoint:** `PATCH /users/{user_id}`

**Change:** `avatar_url` now rejects any value that does not start with `https://`. Non-HTTPS
values return:

```
HTTP 422
{"detail": "avatar_url must start with https://"}
```

**Frontend action required:**
- Validate that avatar URLs use `https://` before submitting.
- Display validation error if the user pastes an `http://` or `javascript:` URL.

---

## 4. Text field length limits — new 422 on long input

**Endpoints:** `POST /games/`, `PATCH /games/{game_id}`

**Fields capped at 2000 characters each:** `description`, `objective`, `setup`, `rules`

Submitting a value over the limit returns `HTTP 422`.

**Frontend action required:**
- Add `maxLength={2000}` to all four textarea inputs in the game creation and edit forms.
- Optionally show a live character counter.

---

## 5. `PATCH /users/complete-profile` — now actually saves

**Change:** This endpoint was silently a no-op — it accepted the request but wrote nothing to the
database. It now correctly saves `date_of_birth` and `country_of_origin`.

**Frontend action required:** None — the frontend was already sending the correct payload.
This is a backend bug fix. Profile completion will now work end-to-end.

> **Important:** `date_of_birth` is used to determine age-based content filtering (see §6).
> Users who have not completed their profile are treated as under-18 for content purposes.

---

## 6. Age-based content filtering — games list and detail

**Endpoints affected:**
- `GET /games/`
- `GET /games/{game_id}`

### `GET /games/` — fewer results for anonymous / under-18 users

Games are hidden from anonymous users, users under 18, and users without a DOB on file when they:
- Have an `18+` age rating, or
- Are flagged `has_adult_content = true` — set when a game contains drinking mechanics, sexual
  references, or explicit profanity, **regardless of what age rating the contributor chose**

The second rule is important: an adult contributor can submit a game containing profanity tagged
as "All Ages". That game will still be hidden from minors via the `has_adult_content` flag.

This is applied server-side. The response shape is unchanged — there are just fewer items.

**Frontend action required:** None for the list itself. However, if the frontend has any
"show all games" toggle or client-side filter that assumes the full catalogue is available,
that assumption no longer holds for non-adult sessions.

### `GET /games/{game_id}` — new 403 for age-restricted games

If a user directly navigates to a game that is age-restricted and they are anonymous or
under-18, the API now returns:

```
HTTP 403 Forbidden
{"detail": "You do not have permission to access this resource"}
```

**Frontend action required:**
- Handle `403` on the game detail page.
- Show an appropriate message: e.g. "This game is not available for your account."
- Do not show a 404-style "game not found" message — the game exists, the user just can't see it.

---

## 7. Content moderation — new 422 on game submission and editing

**Endpoints affected:**
- `POST /games/`
- `PATCH /games/{game_id}` *(text fields only — see below)*
- `POST /optimise/`

### New 422 response: hate speech (all users)

If the submitted text is flagged for hate speech or discriminatory language:

```
HTTP 422
{"detail": "Content violates community guidelines."}
```

### New 422 response: mature content submitted by under-18 user

If the authenticated user is under 18 and the submission contains adult language, sexual
references, or profanity:

```
HTTP 422
{"detail": "You must be 18 or over to submit games containing mature or explicit content."}
```

**Frontend action required:**
- Handle `422` on game create and edit forms, distinct from validation errors.
- Display the `detail` string directly — it is user-safe and intentionally descriptive.
- On the optimise endpoint, handle `422` and show the `detail` string.

### `PATCH /games/{game_id}` — moderation only on text changes

Moderation only runs when `name`, `description`, `objective`, `setup`, or `rules` are included
in the PATCH body. Patching only `is_public`, `age_rating`, `difficulty`, `equipment`,
`game_setting`, etc. skips moderation entirely.

### `PATCH /games/{game_id}` — `description` field is now patchable

**Bug fix:** `description` was missing from the accepted PATCH fields and was silently ignored.
It is now correctly patchable. If the frontend was working around this (e.g. requiring a full
game re-submit to update the description), that workaround can be removed.

---

## 8. Google OAuth — CSRF fix (no frontend action required)

A `state` parameter is now generated server-side and validated on callback. This is fully
transparent to the frontend — the OAuth redirect and callback URLs are unchanged.

**Side effect — OAuth should now work in production.** A cookie `secure`/`samesite`
inconsistency (`ENV` vs `ENVIRONMENT` env var mismatch) was causing `SameSite=None` without
`Secure=true` in production, which browsers reject. This is now fixed. If Google OAuth was
silently failing in production, it should work after this deploy.

---

## 9. Game reporting — new `POST /games/{game_id}/report`

**Auth:** Required.

**Request body:**
```json
{"reason": "Inappropriate Content"}
```

Valid `reason` values (must be sent exactly as shown):
- `"Inappropriate Content"`
- `"Adult Content"`
- `"Spam"`
- `"Inaccurate"`
- `"Other"`

**Responses:**

| Status | Meaning |
|--------|---------|
| `201` | Report saved. Body: `{"message": "Report received."}` |
| `400` | Cannot report your own game |
| `400` | Already reported this game (one report per user per game) |
| `401` | Not authenticated |
| `404` | Game not found |
| `422` | Missing or invalid `reason` |

**Frontend action required:**
- Wire a "Report" button on game detail pages.
- Show the 5 reason options as a select/radio — do not allow free text.
- On 400 "already reported", show a message like "You've already reported this game."
- On 400 "own game", this should not be reachable if the UI hides the button for your own games — add that guard if missing.
- No auto-hide on report — the game remains visible until admin reviews.

---

## 10. Generic error messages on 500s

**Change:** Internal server errors no longer leak database details (table names, column names,
constraint names). All 500 responses now return:

```json
{"detail": "An unexpected error occurred"}
```

**Frontend action required:** None — the frontend should not have been parsing 500 detail
strings. If it was, update that code to handle the generic message.

---

## Summary table

| Endpoint | Method | What changed | Frontend handles |
|---|---|---|---|
| `/auth/token` | POST | Rate limited 5/min | 429 |
| `/users/register/` | POST | Rate limited 3/min | 429 |
| `/users/{id}` | DELETE | 204 → 200 with body | status check |
| `/users/{id}` | PATCH | avatar_url https:// required | 422 validation |
| `/users/complete-profile` | PATCH | Now actually saves | nothing (bug fix) |
| `/games/` | GET | Age filter applied | fewer results |
| `/games/{id}` | GET | 403 for age-restricted | 403 handling |
| `/games/` | POST | Moderation gate + age gate | 422 with detail |
| `/games/{id}` | PATCH | Moderation gate (text fields), description now patchable | 422 with detail |
| `/optimise/` | POST | Moderation gate | 422 with detail |
| `/auth/oauth/google` | GET | CSRF state param added (server-side) | nothing |
| `/games/{id}/report` | POST | New endpoint — report a game | 201/400/401/404/422 |
