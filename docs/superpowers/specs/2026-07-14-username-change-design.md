# Username Change After Registration — Design

**Date:** 2026-07-14
**Branch:** TBD (cut fresh from master)
**Status:** Approved

---

## Context

OAuth signups (Apple with hidden email, Google) get an auto-generated username via
`generate_unique_username(db, email.split("@")[0])` in `src/api/auth.py`. When Apple relays a hidden
email (`abc123@privaterelay.appleid.com`), the resulting username is ugly and meaningless to the user.
There is currently no way to change a username after account creation — `UserUpdate`
(`src/models/user_models/user.py`) has no `username` field, and `PATCH /users/me`
(`src/api/users.py`) never touches it.

This adds username-change support to the existing profile-update endpoint. It is a general capability
(any user, any time), not limited to a one-time "complete registration" step — the frontend's
complete-registration screen for OAuth users is expected to call this alongside
`POST /users/me/complete-profile` (DOB/country), but that endpoint itself is untouched.

---

## Why this needs care: JWT `sub` is the username, not a user ID

Access tokens are minted with `data={"sub": user.username, ...}` (`create_access_token`, used in
`/token`, `/refresh`, and all OAuth exchange endpoints). Every authenticated request resolves the user
via `db.query(User).filter(func.lower(User.username) == token_data.username.lower())`
(`get_current_user`, `src/api/users.py`).

If a user's username changes and their existing token still carries the old `sub`, the very next
authenticated request fails lookup and the user is logged out with no clear reason. `PATCH /users/me`
must therefore issue a fresh token immediately when the username changes, and the frontend must swap
to it.

---

## Model changes (`src/models/user_models/user.py`)

`UserUpdate` gains:

```python
username: Optional[str] = None

@field_validator('username')
@classmethod
def validate_username(cls, v):
    if v is None:
        return v
    if not re.fullmatch(r'[A-Za-z0-9_]{3,30}', v):
        raise ValueError('username must be 3-30 characters, letters/numbers/underscore only')
    if detect_profanity(v):
        raise ValueError('username is not allowed')
    return v
```

(`detect_profanity` imported from `src.utils.age_filter` — existing regex/leetspeak profanity check,
already used unconditionally would be new for this call site: today it's only invoked when the
current user is a minor, gating adult *game content*. For usernames it is applied unconditionally
regardless of the acting user's age, since a username is always public.)

`UserPrivateRead` gains:

```python
access_token: Optional[str] = None
```

Populated only when the PATCH changed the username; `None`/omitted otherwise. Web clients ignore it
(they use the refreshed cookie); mobile bearer-token clients read it and replace their stored token.

---

## Endpoint changes (`PATCH /users/me`, `src/api/users.py`)

Current handler (`update_my_profile`) already does an email-uniqueness check ad hoc before the
generic `setattr` loop. Add an equivalent block for `username`:

1. If `"username" in update_data`:
   - Case-insensitive uniqueness check, excluding self:
     ```python
     db.query(User).filter(
         func.lower(User.username) == update_data["username"].lower(),
         User.id != current_user.id,
     ).first()
     ```
     → 400 `"Username taken"` if found. (Mirrors the case-insensitive check already used at
     registration; the existing email check in this same handler is case-sensitive — left as is,
     out of scope here.)
   - Track `username_changed = update_data["username"] != current_user.username` before applying.
2. Apply the generic `setattr` loop as today (now including `username`).
3. Commit/refresh as today.
4. If `username_changed`: mint a new token via `create_access_token(data={"sub": current_user.username, "ver": current_user.token_version or 0})`, set it on the response cookie exactly as `/token`/`/refresh` do (`httponly`, `secure=IS_PRODUCTION`, `samesite`, `max_age=TOKEN_EXPIRES_MINUTES * 60`).
5. Build the response body as `UserPrivateRead.model_validate(current_user).model_dump()`, then set
   `access_token` in that dict when `username_changed` (avoids assigning a non-column transient
   attribute onto the SQLAlchemy instance — return a plain dict, which FastAPI validates against
   `response_model` the same as an ORM object).

No change to `token_version` — username change is not a revocation event for *other* sessions, it
only invalidates the `sub` claim's ability to resolve, which is exactly what the reissued token fixes
for the session making the change. Other logged-in sessions (e.g. a second device) will fail lookup
on their next request with the old username and simply need to re-login — this is accepted as
correct behavior (their cached username is genuinely stale), not a bug.

No format/profanity validation is added to `UserCreate.username` (registration) — out of scope; only
the change path is constrained.

---

## Testing (`tests/api/users/test_users_patch.py`)

| Test case | Expected |
|-----------|----------|
| Change to valid unused username | 200, `username` updated, `access_token` present and different from old, `Set-Cookie` present |
| New token from response works on next authenticated request | 200 (not 401) |
| Old token fails on next authenticated request after change | 401 |
| Duplicate username, different case (`Existing` vs `existing`) | 400 "Username taken" |
| Same username re-submitted (no-op) | 200, `access_token` absent/`None`, no new cookie |
| Format: too short (<3), too long (>30), invalid chars (space, `@`, `-`) | 422 |
| Profane username (e.g. a word from the existing `_PROFANITY_PATTERNS` list, any case/leetspeak) | 422 |
| PATCH with no `username` key (other fields only) | 200, unrelated fields updated, `access_token` absent |

---

## Out of scope

- Rate limiting / cooldown on repeated username changes (none added — unlimited changes allowed).
- Retroactive format/profanity validation on existing usernames or on `UserCreate`.
- Changes to `POST /users/me/complete-profile` — frontend wires the username field into its own
  registration-completion screen using this same `PATCH /users/me` call.
