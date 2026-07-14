# Username Change — Frontend Integration

## Overview

Two entry points for changing a username:

1. **OAuth onboarding** — new Apple/Google signups get an auto-generated username. The complete-profile
   screen lets them review/edit it in the same request as DOB/country.
2. **Settings screen** — any logged-in user can change their username later via `PATCH /users/me`.

Both endpoints return a fresh `access_token` in the response body (and set a fresh cookie) **only**
when the username actually changed, because the JWT's `sub` claim is the username itself. Mobile
bearer-token clients must replace their stored token when `access_token` is non-null in the response.
Web clients can ignore the body field — the refreshed cookie is set automatically.

---

## Flow 1 — OAuth Complete-Profile

**Trigger:** new Apple/Google signup. Backend redirects to `{FRONTEND_URL}/complete-profile?code=<code>`.

**Step 1:** Exchange the code for a token:

```
POST /auth/exchange?code=<code>
```

Response: `{ "access_token": "...", "token_type": "bearer" }`. Store this token (mobile) — the cookie
is also set automatically for web.

**Step 2:** Fetch the auto-generated username to prefill the form:

```
GET /users/me
Authorization: Bearer <token>
```

Response includes `username` (e.g. `"abc123_4"` for a hidden Apple relay email). Prefill an editable
username input with this value alongside the DOB and country fields. Most users will leave it
unchanged — the field exists so they can edit it if they want.

**Step 3:** Submit the complete-profile form:

```
POST /users/me/complete-profile
Content-Type: application/json

{
  "date_of_birth": "1995-06-15",
  "country_of_origin": "US",
  "username": "abc123_4"
}
```

`username` is optional — omit it (or send the unchanged value) if the user didn't edit it. Sending the
unchanged value is safe and treated as a no-op.

**Response (200):**
```json
{
  "firstname": "Jane",
  "lastname": "Doe",
  "email": "jane@example.com",
  "username": "abc123_4",
  "country_of_origin": "US",
  "role": "user",
  "date_of_birth": "1995-06-15",
  "avatar_url": "https://...",
  "access_token": null
}
```

`access_token` is `null`/absent unless the username changed from what the server had — if it changed,
`access_token` is a new JWT and mobile clients must swap their stored token immediately, or the next
authenticated request will fail.

**Errors:**

| Status | Body | Meaning |
|---|---|---|
| 422 | validation error detail | Username fails format (3-30 chars, `[A-Za-z0-9_]`) or profanity check, or DOB implies under-13 |
| 400 | `{"detail": "Username taken"}` | Another user already has this username (case-insensitive) |

---

## Flow 2 — Settings Screen Username Change

**Trigger:** user edits their username from a profile/settings screen at any later point.

```
PATCH /users/me
Content-Type: application/json

{ "username": "new_name" }
```

Same response shape and `access_token` semantics as Flow 1's complete-profile call. Same error cases
(422 format/profanity, 400 duplicate).

---

## Validation Rules Summary

| Rule | Detail |
|---|---|
| Length | 3-30 characters |
| Characters | letters, numbers, underscore only (`[A-Za-z0-9_]`) |
| Profanity | rejected (case/leetspeak-insensitive) |
| Uniqueness | case-insensitive, checked against all other users |
| Changes allowed | unlimited, no cooldown |
