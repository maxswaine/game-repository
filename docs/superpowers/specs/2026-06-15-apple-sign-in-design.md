# Sign in with Apple — Backend Design

**Date:** 2026-06-15
**Branch:** feature/apple-sign-in (cut from master)
**Status:** Approved

---

## Context

Apple requires Sign in with Apple on any iOS app that offers third-party login. This backend already supports Google OAuth via `POST /auth/oauth/google/token`. The Apple implementation follows the same mobile pattern.

---

## Endpoint

```
POST /auth/oauth/apple/token
```

### Request body

```json
{
  "identity_token": "<base64 JWT from Apple>",
  "firstname": "Max",
  "lastname": "Swaine"
}
```

`firstname` and `lastname` are optional. Apple only provides them on the very first sign-in. The iOS app sends them when available; the backend uses them only when creating a new user, and falls back to empty strings otherwise.

### Response

```json
{
  "access_token": "<our JWT>",
  "token_type": "bearer",
  "is_new_user": true
}
```

### Errors

| Code | Condition |
|------|-----------|
| 400  | Invalid or expired identity token |
| 400  | Audience (`aud`) does not match `APPLE_BUNDLE_ID` |
| 400  | Email already linked to a different OAuth provider |

No 401 for inactive users: if the hard-deletion job has run, the row is gone and the user is treated as new. If still within the 30-day window, `_maybe_reactivate` reactivates them (same behaviour as Google).

---

## Token Verification

Apple's `identityToken` is a signed JWT verified using Apple's public JWK Set.

**Steps:**

1. Fetch JWKs from `https://appleid.apple.com/auth/keys`
2. Cache keys in-process for 24 hours; bust cache on unknown `kid`
3. Read `kid` from JWT header, select matching key
4. Verify signature and claims:
   - `iss` == `https://appleid.apple.com`
   - `aud` == `APPLE_BUNDLE_ID`
   - `exp` is in the future
5. Extract `sub` (Apple user ID) and `email`

**Library:** `PyJWT` + `cryptography`

**New env var:** `APPLE_BUNDLE_ID` — the iOS app's Bundle Identifier (e.g. `com.maxswaine.whatsthatgame`). Found in Xcode → target → General → Identity → Bundle Identifier. Must be added to Railway environment.

Token verification is extracted into a standalone function `verify_apple_token(identity_token: str) -> dict` so tests can mock it cleanly.

---

## User Lookup and Creation

Mirrors `google_token_exchange` exactly:

1. Query `User` by `oauth_provider == "apple"` AND `oauth_id == sub`
2. If found and inactive: call `_maybe_reactivate`, refresh
3. If not found: check for email conflict (existing user with same email, different provider) → 400
4. If not found and no conflict: create new `User`:
   - `oauth_provider = "apple"`
   - `oauth_id = sub`
   - `email` = whatever Apple sent (relay or real — both accepted)
   - `firstname` / `lastname` from request body, empty string fallback
   - `username = generate_unique_username(db, email.split("@")[0])`
   - `avatar_url = None` (Apple never provides one)
   - `hashed_password = None`
5. Issue JWT via `create_access_token`, return `access_token`, `token_type`, `is_new_user`

**No schema changes required.** `oauth_provider` and `oauth_id` columns already exist and are provider-agnostic.

---

## Testing

`verify_apple_token` is mocked in all tests — no real Apple keys or network calls needed.

| Test case | Expected |
|-----------|----------|
| New user, name provided | User created, `is_new_user=true` |
| New user, no name | User created with `firstname=""`, `lastname=""` |
| Existing user, active | JWT issued, `is_new_user=false` |
| Existing user, inactive (within 30 days) | Reactivated, JWT issued |
| Email conflict (existing Google user, same email) | 400 |
| Invalid/expired identity token | 400 |
| Audience mismatch | 400 |

Test files live in `tests/api/auth/` following the existing pattern.

---

## Privacy Policy Updates Required

The following items must be added to or updated in the app's privacy policy before App Store submission:

1. **Sign in with Apple** — state that users may authenticate via Apple ID, and that the Apple-provided email (which may be a private relay address) is stored and used as the account identifier.
2. **Email relay addresses** — clarify that Apple's Hide My Email relay addresses are accepted and treated the same as real email addresses for account purposes.
3. **Name data** — note that first and last name provided by Apple at sign-up are stored as part of the user profile.
4. **Account deletion** — confirm that deleting an account removes all associated personal data including the Apple-linked email and user ID (`sub`), within 30 days of the deletion request. (Required by App Store Review Guideline 5.1.1.)
5. **Third-party identity providers** — if not already present, add a section listing all sign-in providers (Google, Apple) and linking to their respective privacy policies.
