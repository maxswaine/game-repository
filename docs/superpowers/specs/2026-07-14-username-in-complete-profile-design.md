# Username Field in Complete-Profile — Design

**Date:** 2026-07-14
**Branch:** TBD (cut fresh from master)
**Status:** Approved

---

## Context

`PATCH /users/me` (shipped in [[2026-07-14-username-change-design]]) lets any logged-in user change
their username, with uniqueness check, format/profanity validation, and JWT reissue since the token's
`sub` claim is the username.

OAuth signups (Apple/Google) get an auto-generated username via `generate_unique_username(db,
email.split("@")[0])` (`src/api/auth.py`). New OAuth users are redirected to `/complete-profile?code=`
(`src/api/auth.py:367`), which today only collects `date_of_birth` and `country_of_origin`
(`POST /users/me/complete-profile`, `src/api/users.py:139`).

Users currently have no visibility into their auto-generated username until after they land on the
app proper. This adds the username to the same complete-profile screen/call, so OAuth users can
review/edit it as part of onboarding, in the same request as DOB/country.

---

## Model changes (`src/models/user_models/user.py`)

Extract the format+profanity check out of `UserUpdate.validate_username` into a standalone function:

```python
def _validate_username_format(v: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9_]{3,30}', v):
        raise ValueError('username must be 3-30 characters, letters/numbers/underscore only')
    if detect_profanity(v):
        raise ValueError('username is not allowed')
    return v
```

`UserUpdate.validate_username` becomes:

```python
@field_validator('username')
@classmethod
def validate_username(cls, v):
    if v is None:
        return v
    return _validate_username_format(v)
```

`UserCompleteProfile` gains:

```python
username: Optional[str] = None

@field_validator('username')
@classmethod
def validate_username(cls, v):
    if v is None:
        return v
    return _validate_username_format(v)
```

`date_of_birth` and `country_of_origin` on `UserCompleteProfile` stay required — unchanged.

No changes to `UserPrivateRead` — it already has `access_token: Optional[str] = None` from the prior
username-change work, and `complete_profile`'s `response_model` is already `UserPrivateRead`.

---

## Endpoint changes (`src/api/users.py`)

Extract the uniqueness-check-and-flag block currently inline in `update_my_profile` into a shared
helper:

```python
def _check_username_available(db: Session, current_user: User, new_username: str) -> bool:
    """Returns True if new_username differs from current and is free (case-insensitive).
    Raises 400 if taken by another user."""
    if new_username == current_user.username:
        return False
    existing = db.query(User).filter(
        func.lower(User.username) == new_username.lower(),
        User.id != current_user.id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username taken")
    return True
```

`update_my_profile` calls this in place of its current inline block (behavior unchanged).

`complete_profile` (`src/api/users.py:139`) rewritten to:

1. `update_data = profile_data.model_dump(exclude_unset=True)` in place of the current direct
   attribute assignment, so an omitted `username` doesn't touch anything.
2. If `"username" in update_data`: call `_check_username_available(db, current_user,
   update_data["username"])` → `username_changed`. Apply it to `current_user.username` if changed.
3. Apply `date_of_birth` / `country_of_origin` as today (both still required by the model, so always
   present).
4. Commit/refresh as today.
5. Build response body and token-reissue/cookie exactly as `update_my_profile` does (`body =
   UserPrivateRead.model_validate(current_user).model_dump()`; if `username_changed`, mint token via
   `create_access_token`, set `body["access_token"]`, set the `access_token` cookie with the same
   `httponly`/`secure`/`samesite`/`max_age` params).

Route decorator's `responses` dict gains `400: {"description": "Username taken"}` alongside the
existing (currently unenforced) "Profile already complete" description.

---

## Frontend doc

New file: `docs/frontend/username-change-integration.md`. Covers:

- OAuth signup redirect (`/complete-profile?code=`) → exchange code → `GET /users/me` to read the
  auto-generated `username` → prefill an editable username field alongside the existing DOB/country
  fields → single `POST /users/me/complete-profile` submits all three.
- If the response's `access_token` is non-null, mobile bearer-token clients must replace their stored
  token (web clients rely on the refreshed cookie, same as the existing `PATCH /users/me` doc note).
- Also documents `PATCH /users/me` for username edits made later from a settings/profile screen
  (already-shipped capability — this doc did not exist yet, so it's included here for completeness).
- Validation rules surfaced to the frontend: 3-30 chars, `[A-Za-z0-9_]` only, no profanity, 400
  "Username taken" on conflict (case-insensitive).

---

## Testing (`tests/api/users/test_users_complete_profile.py`)

| Test case | Expected |
|-----------|----------|
| Complete profile with valid unused username + DOB/country | 200, `username` updated, `access_token` present, `Set-Cookie` present |
| Complete profile with username omitted | 200, username unchanged, `access_token` absent |
| Complete profile with same username as current | 200, `access_token` absent, no new cookie |
| Duplicate username, different case | 400 "Username taken" |
| Format: too short/long/invalid chars | 422 |
| Profane username | 422 |
| New token from response works on next authenticated request | 200 (not 401) |

---

## Out of scope

- No change to `is_new_user` / OAuth redirect logic in `src/api/auth.py`.
- No "profile already complete" guard added (pre-existing gap, not introduced or fixed here).
- Rate limiting on username changes — still none, consistent with [[2026-07-14-username-change-design]].
