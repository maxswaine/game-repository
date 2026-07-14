# OAuth Duplicate Email Fix — Design

## Problem

A user can end up with two accounts sharing the same email: one password-based (or Apple)
and one Google. `/register` blocks duplicate emails, and `/auth/oauth/apple/token` already
rejects if the email belongs to another account — but `/auth/oauth/google/callback` and
`/auth/oauth/google/token` only look up users by `(oauth_provider, oauth_id)`. If no
matching Google account exists yet, they create a new `User` row with no check that the
email is already registered under another method.

The `users.email` DB column also has no unique constraint (only `username` and `oauth_id`
do), so nothing stops this at the database layer either.

## Fix

**1. Reject duplicate email on Google OAuth signup** (`src/api/auth.py`)

In `google_callback` and `google_token_exchange`, right before creating a new `User` (the
`is_new_user` branch), add the same guard Apple has:

```python
existing = db.query(User).filter(func.lower(User.email) == func.lower(email)).first()
if existing:
    raise HTTPException(status_code=400, detail="Email already linked to another account")
```

**2. Align Apple's existing check to case-insensitive**

`apple_token_exchange`'s current check (`User.email == email`) is case-sensitive. Update it
to the same `func.lower(...)` comparison for consistency across all three signup paths.

**3. Add DB-level unique constraint on `email`**

- `src/db/tables.py`: change `email = Column(String, nullable=False)` to
  `email = Column(String, nullable=False, unique=True)`. This makes `create_all` correct for
  any fresh database (new environments, CI, local dev).
- Since `create_all` never alters existing tables, this alone won't apply to the already-
  existing Railway Postgres `users` table. Since there's no real user data yet (pre-launch),
  run one manual statement against Railway Postgres as part of this deploy:
  ```sql
  ALTER TABLE users ADD CONSTRAINT users_email_key UNIQUE (email);
  ```
  This is a manual, one-time operational step — not automated by this change, and not run by
  Claude Code. The user will run it directly against Railway.

## Non-goals

- Account linking (attaching a second oauth provider to an existing account) — explicitly
  rejected in favor of the simpler reject-on-conflict approach, matching Apple's existing
  behavior.
- Migrating/deduplicating existing rows — not needed pre-launch; no duplicate emails exist
  yet.

## Tests

Add to `tests/api/auth/test_google_oauth_native.py`:
- `test_google_token_duplicate_email_returns_400` — existing password-based user with email
  X, then a Google token exchange callback with claims for the same email (different
  `oauth_id`) → expect 400 `"Email already linked to another account"`, and confirm no new
  user row was created.

Add equivalent case to `tests/api/auth/test_apple_sign_in.py` if not already covered (check
existing file first — Apple's guard already exists, so a test may already be present;
otherwise add one to lock in the case-insensitive fix from item 2).

Add a browser-flow (`google_callback`) duplicate-email test alongside the native one if
`test_google_oauth_native.py` doesn't already cover both entry points — otherwise add to
whichever file covers `/auth/oauth/google/callback`.
