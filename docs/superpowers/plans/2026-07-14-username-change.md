# Username Change After Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a logged-in user change their username via `PATCH /users/me`, so OAuth users (especially Apple with hidden email) can replace an auto-generated username, without breaking their session.

**Architecture:** Add a `username` field + validator to `UserUpdate` (format + profanity check, reusing existing `detect_profanity`). Add an `access_token` field to `UserPrivateRead`. In the `PATCH /users/me` handler, do a case-insensitive uniqueness check on username change, then — because the JWT `sub` claim is the username itself — mint and return a fresh access token (body + cookie) whenever the username actually changes.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy, PyJWT (existing `create_access_token`), pytest + `TestClient`.

## Global Constraints

- Username format: 3-30 chars, `[A-Za-z0-9_]` only.
- Username uniqueness check is case-insensitive (`func.lower(...)`), matching registration's existing check.
- Profanity check uses the existing `detect_profanity()` from `src/utils/age_filter.py`, applied unconditionally (not age-gated).
- No new dependencies, no new env vars, no DB schema changes.
- No rate limit / cooldown on username changes.
- Spec: `docs/superpowers/specs/2026-07-14-username-change-design.md`

---

### Task 1: Model changes — `username` on `UserUpdate`, `access_token` on `UserPrivateRead`

**Files:**
- Modify: `src/models/user_models/user.py`
- Test: `tests/api/users/test_users_patch.py`

**Interfaces:**
- Produces: `UserUpdate.username: Optional[str]` — validated field, raises `ValueError` (→ 422 at the API layer) on bad format or profanity.
- Produces: `UserPrivateRead.access_token: Optional[str] = None` — new field, and `UserPrivateRead.model_config = ConfigDict(from_attributes=True)` so `UserPrivateRead.model_validate(orm_obj)` works without passing `from_attributes=True` at each call site.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/users/test_users_patch.py`:

```python
def test_username_rejects_too_short():
    with pytest.raises(ValidationError):
        UserUpdate(username="ab")


def test_username_rejects_too_long():
    with pytest.raises(ValidationError):
        UserUpdate(username="a" * 31)


def test_username_rejects_invalid_characters():
    with pytest.raises(ValidationError):
        UserUpdate(username="bad name!")


def test_username_rejects_profanity():
    with pytest.raises(ValidationError):
        UserUpdate(username="fuckface")


def test_username_accepts_valid_value():
    model = UserUpdate(username="cool_user_42")
    assert model.username == "cool_user_42"


def test_username_accepts_none():
    model = UserUpdate(username=None)
    assert model.username is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/users/test_users_patch.py -v`
Expected: `UserUpdate` doesn't declare `username` yet, and Pydantic v2's default `extra` behavior is "ignore" (not "forbid"), so passing `username=...` is silently dropped rather than raising at construction time. Result:
- `test_username_rejects_too_short`, `_too_long`, `_invalid_characters`, `_profanity` (each wrapped in `pytest.raises(ValidationError)`) FAIL with `Failed: DID NOT RAISE <class 'pydantic_core._pydantic_core.ValidationError'>`.
- `test_username_accepts_valid_value` FAILS with `AttributeError: 'UserUpdate' object has no attribute 'username'` (the field was never set).
- `test_username_accepts_none` passes trivially either way (ignore it for this check).

- [ ] **Step 3: Add the `username` field + validator to `UserUpdate`, and `access_token` + config to `UserPrivateRead`**

In `src/models/user_models/user.py`, replace the import block (currently lines 1-7):

```python
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

import pycountry
from pydantic import ConfigDict, BaseModel, field_validator

from src.utils.age_filter import detect_profanity
```

Replace the `UserPrivateRead` class (currently lines 77-85):

```python
class UserPrivateRead(BaseModel):
    firstname: str
    lastname: str
    email: str
    username: str
    country_of_origin: str
    role: str
    date_of_birth: Optional[str] = None
    avatar_url: Optional[str] = None
    access_token: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)
```

In `UserUpdate` (currently lines 99-123), add the `username` field and its validator:

```python
class UserUpdate(BaseModel):
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    email: Optional[str] = None
    username: Optional[str] = None
    country_of_origin: Optional[str] = None
    date_of_birth: Optional[str] = None
    avatar_url: Optional[str] = None

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

    @field_validator('avatar_url')
    @classmethod
    def validate_avatar_url(cls, v):
        if v is not None and not v.startswith('https://'):
            raise ValueError('avatar_url must start with https://')
        return v

    @field_validator('date_of_birth')
    @classmethod
    def validate_date_of_birth(cls, v):
        if v is None:
            return v
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except ValueError:
            raise ValueError(date_of_birth_error)
        return v
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/api/users/test_users_patch.py -v`
Expected: all `test_username_*` and `test_avatar_url_*` tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/models/user_models/user.py tests/api/users/test_users_patch.py
git commit -m "feat(users): add username field/validator and access_token response field"
```

---

### Task 2: `PATCH /users/me` — uniqueness check, apply, token reissue

**Files:**
- Modify: `src/api/users.py:1-22` (import block) and `src/api/users.py:163-192` (`update_my_profile`)
- Test: `tests/api/users/test_users_patch.py`

**Interfaces:**
- Consumes: `UserUpdate.username: Optional[str]` and `UserPrivateRead` (incl. `access_token`, `model_config`) from Task 1. `create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str` from `src.core.security` (existing). `TOKEN_EXPIRES_MINUTES: int` from `src.core.security` (existing).
- Produces: `PATCH /users/me` now accepts `username` in the body; returns `access_token` (non-null) and sets a fresh `access_token` cookie only when the username actually changed.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/users/test_users_patch.py`. First add these imports at the top of the file (alongside the existing `import pytest` / `from pydantic import ValidationError` / `from src.models.user_models.user import UserUpdate`):

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

Then append the test functions:

```python
def test_change_username_success(client_with_auth, test_user, db):
    response = client_with_auth.patch("/users/me", json={"username": "brand_new_name"})

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "brand_new_name"
    assert data["access_token"] is not None
    assert "access_token" in response.cookies

    db.refresh(test_user)
    assert test_user.username == "brand_new_name"


def test_change_username_duplicate_case_insensitive_rejected(client_with_auth, second_user):
    response = client_with_auth.patch("/users/me", json={"username": second_user.username.upper()})

    assert response.status_code == 400
    assert response.json()["detail"] == "Username taken"


def test_change_username_same_value_is_noop(client_with_auth, test_user):
    response = client_with_auth.patch("/users/me", json={"username": test_user.username})

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] is None
    assert "access_token" not in response.cookies


def test_patch_other_fields_does_not_reissue_token(client_with_auth):
    response = client_with_auth.patch("/users/me", json={"firstname": "Newname"})

    assert response.status_code == 200
    data = response.json()
    assert data["firstname"] == "Newname"
    assert data["access_token"] is None
    assert "access_token" not in response.cookies


def test_new_token_from_username_change_works(client_no_auth, test_user):
    old_token = _make_token(test_user.username, ver=test_user.token_version or 0)
    change_response = client_no_auth.patch(
        "/users/me",
        json={"username": "renamed_user"},
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

Run: `pytest tests/api/users/test_users_patch.py -v`
Expected: after Task 1, `UserUpdate.username` exists so the old handler's generic `model_dump(exclude_unset=True)` + `setattr` loop already applies a username change — but with **no uniqueness check and no token reissue**. Specifically:
- `test_change_username_success` FAILS — `data["access_token"] is not None` is false (old handler never mints a token) and no cookie is set.
- `test_change_username_duplicate_case_insensitive_rejected` FAILS — returns 200 instead of 400 (no uniqueness check yet; `"OTHERUSER"` and `"otheruser"` are different strings so even SQLite's case-sensitive unique constraint doesn't block it).
- `test_change_username_same_value_is_noop` PASSES already — the old handler never reissues a token regardless of input, which happens to already match this test's expectation.
- `test_patch_other_fields_does_not_reissue_token` PASSES already, same reason.
- `test_new_token_from_username_change_works` FAILS — the PATCH response's `access_token` is `None`, so the follow-up request sends header `Authorization: Bearer None` and gets 401 instead of the expected 200.

Two of the five tests passing before the implementation step is expected here — they're regression guards for behavior the old code already happens to satisfy — proceed to Step 3 regardless.

- [ ] **Step 3: Update imports and add `IS_PRODUCTION` in `src/api/users.py`**

Replace the import block at the top of `src/api/users.py` (currently lines 1-22, everything before `class MessageResponse`):

```python
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Depends
from src.core.limiter import limiter

logger = logging.getLogger(__name__)
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from src.core.exceptions import USER_NOT_FOUND_EXCEPTION, INACTIVE_USER_EXCEPTION, UNAUTHORIZED_EXCEPTION, FORBIDDEN_EXCEPTION
from src.models.enums.role_enum import Role
from src.core.security import verify_access_token, hash_password, verify_password, create_access_token, TOKEN_EXPIRES_MINUTES
from src.db.database import get_db
from src.db.tables import User
from src.models.user_models.user import UserCreate, UserPublicRead, UserPrivateRead, UserCompleteProfile, UserUpdate, \
    UserPasswordUpdate

IS_PRODUCTION = os.getenv("ENV") == "production"
```

- [ ] **Step 4: Rewrite `update_my_profile`**

Replace the handler (currently lines 163-192):

```python
@router.patch("/me", response_model=UserPrivateRead, status_code=200,
              responses={400: {"description": "Email already in use, or Username taken"}})
def update_my_profile(
        updates: UserUpdate,
        current_user: Annotated[User, Depends(get_current_active_user)],
        db: Annotated[Session, Depends(get_db)],
):
    update_data = updates.model_dump(exclude_unset=True)

    if "email" in update_data:
        existing_user = db.query(User).filter(
            User.email == update_data["email"],
            User.id != current_user.id
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail="Email already in use"
            )

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

    for key, value in update_data.items():
        if value is not None:
            setattr(current_user, key, value)

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

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/api/users/test_users_patch.py -v`
Expected: all tests PASS, including the pre-existing `test_avatar_url_*` and Task 1's `test_username_*` tests.

- [ ] **Step 6: Run the full test suite to check for regressions**

Run: `pytest -v`
Expected: all tests PASS (in particular `tests/api/users/`, `tests/api/auth/`, `tests/api/games/` — nothing else reads `UserPrivateRead` or calls `PATCH /users/me`, but confirm no breakage).

- [ ] **Step 7: Commit**

```bash
git add src/api/users.py tests/api/users/test_users_patch.py
git commit -m "feat(users): support username change on PATCH /users/me with token reissue"
```

---

## Self-Review Notes

- Spec coverage: model validation (Task 1), uniqueness check (Task 2), token reissue + cookie (Task 2), response shape (Task 1+2), all spec test-table rows (Task 2 tests) — all covered. Frontend integration (complete-profile screen calling this endpoint) is explicitly out of scope per spec, no backend task needed.
- No placeholders — every step has complete code.
- Type/name consistency checked: `UserPrivateRead.access_token`, `UserUpdate.username`, `create_access_token`, `TOKEN_EXPIRES_MINUTES`, `IS_PRODUCTION` all used identically across Task 1 and Task 2.
