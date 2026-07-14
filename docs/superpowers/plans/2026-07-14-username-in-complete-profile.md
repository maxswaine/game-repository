# Username Field in Complete-Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let OAuth users review/edit their auto-generated username as part of the same `POST /users/me/complete-profile` call that sets DOB/country, instead of requiring a separate `PATCH /users/me` call.

**Architecture:** Add an optional `username` field to `UserCompleteProfile`, reusing the same format/profanity validator as `UserUpdate.username` (extracted into a shared function). In `complete_profile`, reuse the same uniqueness-check-and-token-reissue logic as `update_my_profile` (extracted into a shared helper), so the two endpoints stay behaviorally identical for username handling.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy, PyJWT (existing `create_access_token`), pytest + `TestClient`.

## Global Constraints

- Username format: 3-30 chars, `[A-Za-z0-9_]` only (unchanged from existing `UserUpdate.username`).
- Username uniqueness check is case-insensitive (`func.lower(...)`), excluding self.
- Profanity check uses the existing `detect_profanity()` from `src/utils/age_filter.py`, applied unconditionally.
- `username` on `UserCompleteProfile` is optional — omitted or unchanged means no-op, no token reissue.
- `date_of_birth` and `country_of_origin` on `UserCompleteProfile` remain required — unchanged.
- No new dependencies, no new env vars, no DB schema changes.
- No rate limit / cooldown on username changes.
- Spec: `docs/superpowers/specs/2026-07-14-username-in-complete-profile-design.md`

---

### Task 1: Extract shared username validator; add `username` to `UserCompleteProfile`

**Files:**
- Modify: `src/models/user_models/user.py`
- Test: `tests/api/users/test_users_complete_profile.py`

**Interfaces:**
- Produces: `_validate_username_format(v: str) -> str` — module-level function in `src/models/user_models/user.py`, raises `ValueError` on bad format/profanity, otherwise returns `v` unchanged. Used by both `UserUpdate.validate_username` and `UserCompleteProfile.validate_username`.
- Produces: `UserCompleteProfile.username: Optional[str] = None` — validated field, raises `ValueError` (→ 422 at the API layer) on bad format or profanity.

- [ ] **Step 1: Write the failing tests**

Add to the top of `tests/api/users/test_users_complete_profile.py` (file currently has no imports):

```python
import pytest
from pydantic import ValidationError

from src.models.user_models.user import UserCompleteProfile
```

Then append:

```python
def test_complete_profile_username_rejects_too_short():
    with pytest.raises(ValidationError):
        UserCompleteProfile(date_of_birth="1990-01-01", country_of_origin="US", username="ab")


def test_complete_profile_username_rejects_invalid_characters():
    with pytest.raises(ValidationError):
        UserCompleteProfile(date_of_birth="1990-01-01", country_of_origin="US", username="bad name!")


def test_complete_profile_username_rejects_profanity():
    with pytest.raises(ValidationError):
        UserCompleteProfile(date_of_birth="1990-01-01", country_of_origin="US", username="fuckface")


def test_complete_profile_username_accepts_valid_value():
    model = UserCompleteProfile(date_of_birth="1990-01-01", country_of_origin="US", username="cool_user_42")
    assert model.username == "cool_user_42"


def test_complete_profile_username_accepts_none():
    model = UserCompleteProfile(date_of_birth="1990-01-01", country_of_origin="US")
    assert model.username is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/users/test_users_complete_profile.py -v`
Expected: `UserCompleteProfile` doesn't declare `username` yet, and Pydantic v2's default `extra` behavior is "ignore", so passing `username=...` is silently dropped rather than raising. Result:
- `test_complete_profile_username_rejects_too_short`, `_invalid_characters`, `_profanity` FAIL with `Failed: DID NOT RAISE <class 'pydantic_core._pydantic_core.ValidationError'>`.
- `test_complete_profile_username_accepts_valid_value` FAILS with `AttributeError: 'UserCompleteProfile' object has no attribute 'username'`.
- `test_complete_profile_username_accepts_none` FAILS the same way (field doesn't exist at all).
- The three pre-existing tests in this file (`test_complete_profile_under_13_returns_422`, `test_complete_profile_saves_dob_and_country`, `test_complete_profile_response_reflects_updated_fields`) still PASS.

- [ ] **Step 3: Extract the shared validator and update both models**

In `src/models/user_models/user.py`, add a module-level function right after `_check_minimum_age` (currently ends at line 21, before `class UserBase`):

```python
def _validate_username_format(v: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9_]{3,30}', v):
        raise ValueError('username must be 3-30 characters, letters/numbers/underscore only')
    if detect_profanity(v):
        raise ValueError('username is not allowed')
    return v
```

Replace `UserUpdate.validate_username` (currently lines 119-128) with:

```python
    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        if v is None:
            return v
        return _validate_username_format(v)
```

Replace the `UserCompleteProfile` class (currently lines 159-172):

```python
class UserCompleteProfile(BaseModel):
    """For OAuth users completing their profile after signup"""
    date_of_birth: str
    country_of_origin: str
    username: Optional[str] = None

    @field_validator('date_of_birth')
    @classmethod
    def validate_date_of_birth(cls, v):
        try:
            dob = datetime.strptime(v, '%Y-%m-%d').date()
        except ValueError:
            raise ValueError(date_of_birth_error)
        _check_minimum_age(dob)
        return v

    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        if v is None:
            return v
        return _validate_username_format(v)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/api/users/test_users_complete_profile.py -v`
Expected: all tests in the file PASS.

Run: `pytest tests/api/users/test_users_patch.py -v`
Expected: all tests still PASS (the `UserUpdate.validate_username` behavior is unchanged, just refactored to call the shared function).

- [ ] **Step 5: Commit**

```bash
git add src/models/user_models/user.py tests/api/users/test_users_complete_profile.py
git commit -m "refactor(users): extract shared username validator, add username to UserCompleteProfile"
```

---

### Task 2: `POST /users/me/complete-profile` — uniqueness check, apply, token reissue

**Files:**
- Modify: `src/api/users.py:139-152` (add helper before this, rewrite `complete_profile`) and `src/api/users.py:187-200` (`update_my_profile`, refactor to use the extracted helper)
- Test: `tests/api/users/test_users_complete_profile.py`

**Interfaces:**
- Consumes: `UserCompleteProfile.username: Optional[str]` from Task 1. `create_access_token`, `TOKEN_EXPIRES_MINUTES`, `IS_PRODUCTION` (all already imported/defined in `src/api/users.py`).
- Produces: `_check_username_available(db: Session, current_user: User, new_username: str) -> bool` — module-level function in `src/api/users.py`. Returns `True` if `new_username` differs from `current_user.username` and is free; raises `HTTPException(400, "Username taken")` if taken by another user; returns `False` if `new_username == current_user.username` (no-op case).
- Produces: `POST /users/me/complete-profile` now accepts optional `username` in the body; returns `access_token` (non-null) and sets a fresh `access_token` cookie only when the username actually changed. Same response shape as `PATCH /users/me`.

- [ ] **Step 1: Write the failing tests**

Add to the top of `tests/api/users/test_users_complete_profile.py`, alongside the Task 1 imports:

```python
from datetime import datetime, timezone, timedelta

import jwt

from src.core.security import SECRET_KEY, ALGORITHM, TOKEN_EXPIRES_MINUTES


def _make_token(username: str, ver: int = 0) -> str:
    payload = {
        "sub": username,
        "ver": ver,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRES_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
```

Then append:

```python
def test_complete_profile_with_username_success(client_with_auth, test_user, db):
    payload = {"date_of_birth": "1990-06-15", "country_of_origin": "US", "username": "brand_new_name"}
    response = client_with_auth.post("/users/me/complete-profile", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "brand_new_name"
    assert data["access_token"] is not None
    assert "access_token" in response.cookies

    db.refresh(test_user)
    assert test_user.username == "brand_new_name"


def test_complete_profile_without_username_keeps_existing(client_with_auth, test_user, db):
    original_username = test_user.username
    payload = {"date_of_birth": "1990-06-15", "country_of_origin": "US"}
    response = client_with_auth.post("/users/me/complete-profile", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == original_username
    assert data["access_token"] is None
    assert "access_token" not in response.cookies


def test_complete_profile_username_duplicate_case_insensitive_rejected(client_with_auth, second_user):
    payload = {
        "date_of_birth": "1990-06-15",
        "country_of_origin": "US",
        "username": second_user.username.upper(),
    }
    response = client_with_auth.post("/users/me/complete-profile", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Username taken"


def test_complete_profile_username_same_value_is_noop(client_with_auth, test_user):
    payload = {
        "date_of_birth": "1990-06-15",
        "country_of_origin": "US",
        "username": test_user.username,
    }
    response = client_with_auth.post("/users/me/complete-profile", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] is None
    assert "access_token" not in response.cookies


def test_complete_profile_new_token_from_username_change_works(client_no_auth, test_user):
    old_token = _make_token(test_user.username, ver=test_user.token_version or 0)
    change_response = client_no_auth.post(
        "/users/me/complete-profile",
        json={"date_of_birth": "1990-06-15", "country_of_origin": "US", "username": "renamed_user"},
        headers={"Authorization": f"Bearer {old_token}"},
    )
    assert change_response.status_code == 200
    new_token = change_response.json()["access_token"]
    assert new_token is not None

    old_token_response = client_no_auth.get(
        "/users/me", headers={"Authorization": f"Bearer {old_token}"}
    )
    assert old_token_response.status_code == 404

    new_token_response = client_no_auth.get(
        "/users/me", headers={"Authorization": f"Bearer {new_token}"}
    )
    assert new_token_response.status_code == 200
    assert new_token_response.json()["username"] == "renamed_user"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/users/test_users_complete_profile.py -v`
Expected: after Task 1, `UserCompleteProfile.username` exists on the model, but the handler ignores it entirely (only ever reads `profile_data.date_of_birth` / `profile_data.country_of_origin`). Specifically:
- `test_complete_profile_with_username_success` FAILS — `data["username"]` is still the original username, and `access_token` is `None`.
- `test_complete_profile_without_username_keeps_existing` PASSES already — the handler never touches username or issues a token regardless of input, which happens to already match this test's expectation.
- `test_complete_profile_username_duplicate_case_insensitive_rejected` FAILS — returns 200 instead of 400 (no uniqueness check yet).
- `test_complete_profile_username_same_value_is_noop` PASSES already, same reason as the "without_username" case.
- `test_complete_profile_new_token_from_username_change_works` FAILS — `access_token` is `None`, so the follow-up request sends `Authorization: Bearer None` and gets 401/404 instead of the expected 200.

Two of the five tests passing before the implementation step is expected — they're regression guards for behavior the old code already happens to satisfy — proceed to Step 3 regardless.

- [ ] **Step 3: Add the shared helper, rewrite `complete_profile`, refactor `update_my_profile`**

In `src/api/users.py`, insert this function immediately before `@router.post("/me/complete-profile"...)` (currently line 139):

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

Replace the `complete_profile` handler (currently lines 139-152) with:

```python
@router.post("/me/complete-profile", response_model=UserPrivateRead, status_code=200,
             responses={401: {"description": "Authentication required"},
                        400: {"description": "Username taken"},
                        422: {"description": "Profile already complete"}})
def complete_profile(
        db: Annotated[Session, Depends(get_db)],
        profile_data: UserCompleteProfile,
        current_user: Annotated[User, Depends(get_current_active_user)],
):
    update_data = profile_data.model_dump(exclude_unset=True)

    username_changed = False
    if "username" in update_data and update_data["username"] is not None:
        username_changed = _check_username_available(db, current_user, update_data["username"])
        if username_changed:
            current_user.username = update_data["username"]

    current_user.date_of_birth = profile_data.date_of_birth
    current_user.country_of_origin = profile_data.country_of_origin
    current_user.last_updated = datetime.now(timezone.utc)

    db.commit()
    db.refresh(current_user)

    body = UserPrivateRead.model_validate(current_user).model_dump()

    if username_changed:
        new_access_token = create_access_token(
            data={"sub": current_user.username, "ver": current_user.token_version or 0}
        )
        body["access_token"] = new_access_token

    response = JSONResponse(content=body)

    if username_changed:
        response.set_cookie(
            key="access_token",
            value=new_access_token,
            httponly=True,
            secure=IS_PRODUCTION,
            samesite="none" if IS_PRODUCTION else "lax",
            max_age=TOKEN_EXPIRES_MINUTES * 60,
        )

    return response
```

Note the `responses` dict's `422` description is left as the pre-existing (unenforced) "Profile already complete" placeholder — no guard for that case exists today and adding one is out of scope for this plan.

In `update_my_profile` (currently lines 187-200), replace the inline uniqueness-check block:

```python
    username_changed = False
    if "username" in update_data:
        new_username = update_data["username"]
        if new_username != current_user.username:
            existing_username = db.query(User).filter(
                func.lower(User.username) == new_username.lower(),
                User.id != current_user.id
            ).first()
            if existing_username:
                raise HTTPException(
                    status_code=400,
                    detail="Username taken"
                )
            username_changed = True
```

with:

```python
    username_changed = False
    if "username" in update_data:
        username_changed = _check_username_available(db, current_user, update_data["username"])
```

The rest of `update_my_profile` is unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/api/users/test_users_complete_profile.py -v`
Expected: all tests PASS.

Run: `pytest tests/api/users/test_users_patch.py -v`
Expected: all tests still PASS (behavior of `update_my_profile` is unchanged, just refactored to call the shared helper).

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `pytest -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/api/users.py tests/api/users/test_users_complete_profile.py
git commit -m "feat(users): support username in complete-profile with token reissue"
```

---

### Task 3: Frontend integration doc

**Files:**
- Create: `docs/frontend/username-change-integration.md`

**Interfaces:**
- Consumes: `POST /users/me/complete-profile` (Task 2), `PATCH /users/me` (already shipped), `GET /users/me` (already shipped).
- Produces: a doc for frontend engineers, styled like `docs/frontend/password-reset-integration.md`.

- [ ] **Step 1: Write the doc**

Create `docs/frontend/username-change-integration.md`:

```markdown
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

\```
POST /auth/exchange?code=<code>
\```

Response: `{ "access_token": "...", "token_type": "bearer" }`. Store this token (mobile) — the cookie
is also set automatically for web.

**Step 2:** Fetch the auto-generated username to prefill the form:

\```
GET /users/me
Authorization: Bearer <token>
\```

Response includes `username` (e.g. `"abc123_4"` for a hidden Apple relay email). Prefill an editable
username input with this value alongside the DOB and country fields. Most users will leave it
unchanged — the field exists so they can edit it if they want.

**Step 3:** Submit the complete-profile form:

\```
POST /users/me/complete-profile
Content-Type: application/json

{
  "date_of_birth": "1995-06-15",
  "country_of_origin": "US",
  "username": "abc123_4"
}
\```

`username` is optional — omit it (or send the unchanged value) if the user didn't edit it. Sending the
unchanged value is safe and treated as a no-op.

**Response (200):**
\```json
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
\```

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

\```
PATCH /users/me
Content-Type: application/json

{ "username": "new_name" }
\```

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
```

- [ ] **Step 2: Commit**

```bash
git add docs/frontend/username-change-integration.md
git commit -m "docs(frontend): add username-change integration guide"
```

---

## Self-Review Notes

- Spec coverage: model changes (Task 1), endpoint changes + shared helper (Task 2), frontend doc (Task 3), all spec test-table rows (Task 2 tests) — all covered.
- No placeholders — every step has complete code.
- Type/name consistency checked: `_validate_username_format`, `_check_username_available`, `UserCompleteProfile.username`, `create_access_token`, `TOKEN_EXPIRES_MINUTES`, `IS_PRODUCTION` used identically across tasks.
