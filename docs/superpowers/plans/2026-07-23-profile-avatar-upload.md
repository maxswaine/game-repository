# Profile Picture Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user upload, replace, and remove their own profile picture via presigned direct-to-R2 upload + OpenAI moderation (fail-closed), reusing the exact storage/moderation infra already shipped for game Photos, and close the two ways `avatar_url` currently gets set without moderation (direct `PATCH /users/me`, and OAuth signup's raw provider picture claim).

**Architecture:** A new `src/api/avatar.py` router (mounted at `/users`) exposes `POST /users/me/avatar/upload-url`, `POST /users/me/avatar`, and `DELETE /users/me/avatar`. It reuses `src/services/storage.py` and `src/services/moderation.check_image` unchanged. `User.avatar_url` gains a single new writer path; `UserUpdate.avatar_url` is removed, and Google OAuth signup stops setting `avatar_url` from the provider's picture claim.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, boto3 (already wired to Cloudflare R2), OpenAI omni-moderation, pytest with SQLite + fully mocked storage/OpenAI.

## Global Constraints

- Reuse `src/services/storage.py` and `src/services/moderation.check_image` **unchanged** — no edits to either module.
- Object key: `users/{user_id}/{uuid4hex}.{ext}`, ext ∈ {jpg, png, webp}. One live avatar object per user (replace-only, no gallery).
- Per-upload cap **5 MB**; content types **image/jpeg, image/png, image/webp**.
- Moderation is fail-closed (inherited from `check_image` — do not change it).
- All three avatar endpoints require auth (401 if missing). There is no separate owner check — the endpoints always act on `current_user`.
- Only delete an old R2 object when the current `avatar_url` starts with `R2_PUBLIC_URL` (i.e. it's one of ours) — never attempt to delete a provider-hosted (Google) URL.
- `UserPrivateRead` is returned by both `register` and `remove` — no dedicated avatar read model.
- Follow existing conventions: `Annotated[Session, Depends(get_db)]`, the `auth_required()` `Depends(get_current_active_user)` helper (as used in `src/api/photos.py`), lazy client construction (already done inside `storage.py`).
- Tests run with `DATABASE_URL="sqlite:///./test.db"` and mock storage + OpenAI — never hit live R2/OpenAI.
- Commit trailer on every commit:
  ```
  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  ```

---

## File Structure

- **Create** `src/models/user_models/avatar.py` — request/response models (mirrors `src/models/game_models/game_photo.py`'s pattern of a dedicated file per feature).
- **Create** `src/api/avatar.py` — avatar write endpoints (router mounted at `/users`).
- **Modify** `src/main.py` — register the avatar router.
- **Modify** `src/models/user_models/user.py` — remove `avatar_url` field + validator from `UserUpdate`.
- **Modify** `src/api/auth.py` — stop Google OAuth signup (web + mobile) from setting `avatar_url` from the picture claim.
- **Create** `tests/api/users/test_avatar.py` — avatar endpoint tests.
- **Modify** `tests/api/users/test_users_patch.py` — remove the 4 tests that exercise `UserUpdate.avatar_url` (field is being deleted), add a regression test that `PATCH /users/me` no longer changes `avatar_url`.
- **Modify** `tests/api/auth/test_google_oauth_native.py` — assert new-user `avatar_url` is `None` despite a non-null `picture` claim.
- **Modify** `tests/api/auth/test_oauth_csrf.py` — add a new success-path test asserting the same for the web OAuth callback.

---

## Task 1: Avatar Pydantic models

**Files:**
- Create: `src/models/user_models/avatar.py`
- Test: `tests/api/users/__init__.py` (already exists — no change), `tests/api/users/test_avatar_models.py`

**Interfaces:**
- Produces:
  - `AvatarUploadUrlRequest(content_type: str)`
  - `AvatarUploadUrlResponse(upload_url: str, object_key: str)`
  - `AvatarRegisterRequest(object_key: str)`

- [ ] **Step 1: Write the failing test**

Create `tests/api/users/test_avatar_models.py`:

```python
from src.models.user_models.avatar import (
    AvatarUploadUrlRequest,
    AvatarUploadUrlResponse,
    AvatarRegisterRequest,
)


def test_avatar_models_construct():
    assert AvatarUploadUrlRequest(content_type="image/jpeg").content_type == "image/jpeg"
    resp = AvatarUploadUrlResponse(upload_url="https://u", object_key="users/u1/a.jpg")
    assert resp.object_key == "users/u1/a.jpg"
    assert AvatarRegisterRequest(object_key="users/u1/a.jpg").object_key == "users/u1/a.jpg"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DATABASE_URL="sqlite:///./test.db" python -m pytest tests/api/users/test_avatar_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.models.user_models.avatar'`

- [ ] **Step 3: Write the models**

Create `src/models/user_models/avatar.py`:

```python
from pydantic import BaseModel


class AvatarUploadUrlRequest(BaseModel):
    content_type: str


class AvatarUploadUrlResponse(BaseModel):
    upload_url: str
    object_key: str


class AvatarRegisterRequest(BaseModel):
    object_key: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `DATABASE_URL="sqlite:///./test.db" python -m pytest tests/api/users/test_avatar_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/models/user_models/avatar.py tests/api/users/test_avatar_models.py
git commit -m "$(cat <<'EOF'
feat(avatar): add avatar upload request/response models

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Close the PATCH bypass on `avatar_url`

**Files:**
- Modify: `src/models/user_models/user.py`
- Modify: `tests/api/users/test_users_patch.py`

**Interfaces:**
- Consumes: none new.
- Produces: `UserUpdate` no longer has an `avatar_url` field. `update_my_profile` (`src/api/users.py:214-265`) needs no code change — its `update_data.items()` / `setattr` loop stops seeing the field once it's gone from the model.

- [ ] **Step 1: Write the failing test**

The four existing tests at the top of `tests/api/users/test_users_patch.py` (lines 20-37) exercise the field being removed and will break once it's gone. Replace them now with a test of the new behavior — a client sending `avatar_url` gets it silently ignored.

In `tests/api/users/test_users_patch.py`, replace lines 20-37 (`test_avatar_url_rejects_javascript_protocol` through `test_avatar_url_accepts_none`) with:

```python
def test_patch_avatar_url_is_ignored(client_with_auth, test_user, db):
    response = client_with_auth.patch(
        "/users/me", json={"avatar_url": "https://example.com/hijack.jpg"}
    )
    assert response.status_code == 200
    db.refresh(test_user)
    assert test_user.avatar_url is None
```

Also remove the now-unused `UserUpdate` import reference check — `UserUpdate` is still imported and used by the username tests further down in the file, so leave the import line (`from src.models.user_models.user import UserUpdate, UserPasswordUpdate`) as-is.

- [ ] **Step 2: Run test to verify it fails as expected**

Run: `DATABASE_URL="sqlite:///./test.db" python -m pytest tests/api/users/test_users_patch.py -v`
Expected: the four old avatar tests are gone (no longer collected). `test_patch_avatar_url_is_ignored` currently FAILS — `PATCH /users/me` still accepts `avatar_url` and sets it, so `test_user.avatar_url` will be the hijack URL, not `None`.

- [ ] **Step 3: Remove `avatar_url` from `UserUpdate`**

In `src/models/user_models/user.py`, remove the field and its validator from `UserUpdate` (lines 118-139 currently):

```python
class UserUpdate(BaseModel):
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    email: Optional[str] = None
    username: Optional[str] = None
    country_of_origin: Optional[str] = None
    date_of_birth: Optional[str] = None

    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        if v is None:
            return v
        return _validate_username_format(v)

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

(This deletes the `avatar_url: Optional[str] = None` field and the `validate_avatar_url` validator; everything else in the class is unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `DATABASE_URL="sqlite:///./test.db" python -m pytest tests/api/users/test_users_patch.py -v`
Expected: PASS (all tests, including `test_patch_avatar_url_is_ignored`)

- [ ] **Step 5: Run the full users test suite to check for regressions**

Run: `DATABASE_URL="sqlite:///./test.db" python -m pytest tests/api/users/ -v`
Expected: PASS (no regressions elsewhere)

- [ ] **Step 6: Commit**

```bash
git add src/models/user_models/user.py tests/api/users/test_users_patch.py
git commit -m "$(cat <<'EOF'
fix(users): remove unmoderated avatar_url bypass from PATCH /users/me

avatar_url could previously be set to any https:// URL directly via
PATCH /users/me, bypassing the moderation the new avatar upload flow
enforces. The field is dropped from UserUpdate entirely; setting an
avatar now only happens through POST /users/me/avatar.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Stop OAuth signup from auto-setting `avatar_url`

**Files:**
- Modify: `src/api/auth.py`
- Modify: `tests/api/auth/test_google_oauth_native.py`
- Modify: `tests/api/auth/test_oauth_csrf.py`

**Interfaces:**
- Consumes: none new.
- Produces: new Google OAuth users (both the web callback at `src/api/auth.py:280` and the mobile token-exchange at `src/api/auth.py:490`) get `avatar_url=None` on creation, regardless of the provider's `picture` claim.

- [ ] **Step 1: Write the failing test (mobile flow)**

In `tests/api/auth/test_google_oauth_native.py`, `test_google_token_new_user_created_in_db` (currently at lines 87-98) already uses `VALID_TOKENINFO`, which includes `"picture": "https://example.com/photo.jpg"`. Add an assertion to it:

```python
def test_google_token_new_user_created_in_db(db):
    client = _client(db)
    try:
        with patch("src.api.auth.httpx.AsyncClient", _async_client_mock(VALID_TOKENINFO)), \
             patch.dict(os.environ, {"GOOGLE_CLIENT_ID": FAKE_CLIENT_ID}):
            client.post("/auth/oauth/google/token", json={"id_token": "fake-id-token"})
        user = db.query(User).filter(User.oauth_id == "google-sub-12345").first()
        assert user is not None
        assert user.email == "testuser@gmail.com"
        assert user.oauth_provider == "google"
        assert user.avatar_url is None
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Write the failing test (web callback flow)**

`tests/api/auth/test_oauth_csrf.py` has no existing test that exercises a *successful* new-user creation through `/auth/oauth/google/callback` (only the CSRF and duplicate-email paths). Add one, following the mocking pattern already used in `test_google_callback_duplicate_email_returns_400`:

Append to `tests/api/auth/test_oauth_csrf.py`:

```python
def test_google_callback_new_user_avatar_url_is_none(oauth_client, db):
    login_resp = oauth_client.get("/auth/oauth/google", follow_redirects=False)
    location = login_resp.headers["location"]
    state = parse_qs(urlparse(location).query)["state"][0]

    mock_token_resp = AsyncMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json = lambda: {"access_token": "fake-google-access-token"}

    mock_userinfo_resp = AsyncMock()
    mock_userinfo_resp.json = lambda: {
        "email": "freshuser@example.com",
        "email_verified": True,
        "sub": "google-sub-fresh-1",
        "given_name": "Fresh",
        "family_name": "User",
        "picture": "https://example.com/photo.jpg",
    }

    with patch("httpx.AsyncClient") as mock_cls:
        instance = mock_cls.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=mock_token_resp)
        instance.get = AsyncMock(return_value=mock_userinfo_resp)
        response = oauth_client.get(
            f"/auth/oauth/google/callback?code=testcode&state={state}",
            follow_redirects=False,
        )

    assert response.status_code in (302, 307)
    user = db.query(User).filter(User.oauth_id == "google-sub-fresh-1").first()
    assert user is not None
    assert user.avatar_url is None
```

- [ ] **Step 3: Run both tests to verify they fail**

Run: `DATABASE_URL="sqlite:///./test.db" python -m pytest tests/api/auth/test_google_oauth_native.py::test_google_token_new_user_created_in_db tests/api/auth/test_oauth_csrf.py::test_google_callback_new_user_avatar_url_is_none -v`
Expected: both FAIL — `assert user.avatar_url is None` fails because it's currently `"https://example.com/photo.jpg"`.

- [ ] **Step 4: Remove the picture-claim assignment from both signup sites**

In `src/api/auth.py`, in `google_callback` (the web OAuth flow), change the `User(...)` construction currently at lines 349-360:

```python
        user = User(
            email=email,
            username=generate_unique_username(db, email.split("@")[0]),
            firstname=userinfo.get("given_name") or "",
            lastname=userinfo.get("family_name") or "",
            created_at=datetime.now(timezone.utc),
            oauth_provider="google",
            oauth_id=oauth_id,
            country_of_origin=None,
            date_of_birth=None
        )
```

(Removes the `avatar_url=userinfo.get("picture"),` line — `avatar_url` is left unset, so it defaults to `None` via the nullable column.)

In `google_token_exchange` (the mobile OAuth flow), change the `User(...)` construction currently at lines 542-553:

```python
        user = User(
            email=email,
            username=generate_unique_username(db, email.split("@")[0]),
            firstname=claims.get("given_name") or "",
            lastname=claims.get("family_name") or "",
            created_at=datetime.now(timezone.utc),
            oauth_provider="google",
            oauth_id=oauth_id,
            country_of_origin=None,
            date_of_birth=None,
        )
```

(Removes the `avatar_url=claims.get("picture"),` line.)

Do **not** touch `apple_token_exchange` (`src/api/auth.py:613-624`) — it already passes `avatar_url=None` explicitly, which is already the value we want.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `DATABASE_URL="sqlite:///./test.db" python -m pytest tests/api/auth/test_google_oauth_native.py::test_google_token_new_user_created_in_db tests/api/auth/test_oauth_csrf.py::test_google_callback_new_user_avatar_url_is_none -v`
Expected: PASS

- [ ] **Step 6: Run the full auth test suite to check for regressions**

Run: `DATABASE_URL="sqlite:///./test.db" python -m pytest tests/api/auth/ -v`
Expected: PASS (no regressions)

- [ ] **Step 7: Commit**

```bash
git add src/api/auth.py tests/api/auth/test_google_oauth_native.py tests/api/auth/test_oauth_csrf.py
git commit -m "$(cat <<'EOF'
fix(auth): stop Google OAuth signup from auto-setting avatar_url

The provider's picture claim was written straight to avatar_url with
no moderation. New OAuth users now get avatar_url=None like password
signups; the upload flow in POST /users/me/avatar becomes the only
way avatar_url gets set after account creation.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Avatar upload/register/remove endpoints

**Files:**
- Create: `src/api/avatar.py`
- Modify: `src/main.py`
- Test: `tests/api/users/test_avatar.py`

**Interfaces:**
- Consumes: `User` (table); `storage.*` (`generate_quarantine_put`, `generate_quarantine_get`, `head_quarantine`, `copy_to_public`, `delete_quarantine`, `delete_public`, `public_url_for`); `check_image` (`src/services/moderation.py`); `AvatarUploadUrlRequest`, `AvatarUploadUrlResponse`, `AvatarRegisterRequest` (Task 1); `UserPrivateRead` (`src/models/user_models/user.py`); `get_current_active_user` (`src/api/users.py`); `R2_PUBLIC_URL` (`src/utils/config.py`).
- Produces: `avatar.router` with
  - `POST /me/avatar/upload-url` → `AvatarUploadUrlResponse`
  - `POST /me/avatar` → `UserPrivateRead`
  - `DELETE /me/avatar` → `UserPrivateRead`
  - module constants `MAX_AVATAR_BYTES = 5 * 1024 * 1024`, `ALLOWED_CONTENT_TYPES`, `EXT_MAP`
  - helper `_delete_if_ours(avatar_url: str | None) -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/api/users/test_avatar.py`:

```python
from unittest.mock import patch

from src.main import app
from src.db.database import get_db


def test_upload_url_happy(client_with_auth, test_user):
    with patch("src.api.avatar.storage.generate_quarantine_put", return_value="https://presigned-put"):
        resp = client_with_auth.post(
            "/users/me/avatar/upload-url", json={"content_type": "image/jpeg"}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["upload_url"] == "https://presigned-put"
    assert body["object_key"].startswith(f"users/{test_user.id}/")
    assert body["object_key"].endswith(".jpg")


def test_upload_url_bad_content_type(client_with_auth):
    resp = client_with_auth.post(
        "/users/me/avatar/upload-url", json={"content_type": "application/pdf"}
    )
    assert resp.status_code == 422


def test_upload_url_requires_auth(client_no_auth):
    resp = client_no_auth.post(
        "/users/me/avatar/upload-url", json={"content_type": "image/jpeg"}
    )
    assert resp.status_code == 401


def _register(client, object_key):
    return client.post("/users/me/avatar", json={"object_key": object_key})


def test_register_happy_sets_avatar_url(client_with_auth, test_user, db):
    key = f"users/{test_user.id}/abc.jpg"
    public = f"https://cdn.example.com/{key}"
    with patch("src.api.avatar.storage.head_quarantine", return_value={"size": 1000, "content_type": "image/jpeg"}), \
         patch("src.api.avatar.storage.generate_quarantine_get", return_value="https://get"), \
         patch("src.api.avatar.check_image", return_value=True), \
         patch("src.api.avatar.storage.copy_to_public") as copy_mock, \
         patch("src.api.avatar.storage.delete_quarantine") as delq_mock, \
         patch("src.api.avatar.storage.public_url_for", return_value=public):
        resp = _register(client_with_auth, key)
    assert resp.status_code == 200
    assert resp.json()["avatar_url"] == public
    copy_mock.assert_called_once_with(key)
    delq_mock.assert_called_once_with(key)

    db.refresh(test_user)
    assert test_user.avatar_url == public


def test_register_replacing_own_r2_avatar_deletes_old_object(client_with_auth, test_user, db):
    old_key = f"users/{test_user.id}/old.jpg"
    test_user.avatar_url = f"https://cdn.example.com/{old_key}"
    db.commit()

    new_key = f"users/{test_user.id}/new.jpg"
    with patch("src.api.avatar.R2_PUBLIC_URL", "https://cdn.example.com"), \
         patch("src.api.avatar.storage.head_quarantine", return_value={"size": 1000, "content_type": "image/jpeg"}), \
         patch("src.api.avatar.storage.generate_quarantine_get", return_value="https://get"), \
         patch("src.api.avatar.check_image", return_value=True), \
         patch("src.api.avatar.storage.copy_to_public"), \
         patch("src.api.avatar.storage.delete_quarantine"), \
         patch("src.api.avatar.storage.delete_public") as delp_mock, \
         patch("src.api.avatar.storage.public_url_for", return_value=f"https://cdn.example.com/{new_key}"):
        resp = _register(client_with_auth, new_key)
    assert resp.status_code == 200
    delp_mock.assert_called_once_with(old_key)


def test_register_replacing_oauth_avatar_does_not_delete(client_with_auth, test_user, db):
    test_user.avatar_url = "https://lh3.googleusercontent.com/a/old-google-avatar.jpg"
    db.commit()

    new_key = f"users/{test_user.id}/new.jpg"
    with patch("src.api.avatar.R2_PUBLIC_URL", "https://cdn.example.com"), \
         patch("src.api.avatar.storage.head_quarantine", return_value={"size": 1000, "content_type": "image/jpeg"}), \
         patch("src.api.avatar.storage.generate_quarantine_get", return_value="https://get"), \
         patch("src.api.avatar.check_image", return_value=True), \
         patch("src.api.avatar.storage.copy_to_public"), \
         patch("src.api.avatar.storage.delete_quarantine"), \
         patch("src.api.avatar.storage.delete_public") as delp_mock, \
         patch("src.api.avatar.storage.public_url_for", return_value=f"https://cdn.example.com/{new_key}"):
        resp = _register(client_with_auth, new_key)
    assert resp.status_code == 200
    delp_mock.assert_not_called()


def test_register_rejects_foreign_key_prefix(client_with_auth, test_user):
    resp = _register(client_with_auth, f"users/{test_user.id}-not-really/x.jpg")
    assert resp.status_code == 422


def test_register_missing_object(client_with_auth, test_user):
    with patch("src.api.avatar.storage.head_quarantine", return_value=None):
        resp = _register(client_with_auth, f"users/{test_user.id}/x.jpg")
    assert resp.status_code == 422


def test_register_oversized(client_with_auth, test_user):
    with patch("src.api.avatar.storage.head_quarantine", return_value={"size": 6 * 1024 * 1024, "content_type": "image/jpeg"}), \
         patch("src.api.avatar.storage.delete_quarantine") as delq_mock:
        resp = _register(client_with_auth, f"users/{test_user.id}/x.jpg")
    assert resp.status_code == 422
    delq_mock.assert_called_once()


def test_register_moderation_reject_deletes_quarantine_no_public_copy(client_with_auth, test_user):
    key = f"users/{test_user.id}/bad.jpg"
    with patch("src.api.avatar.storage.head_quarantine", return_value={"size": 1000, "content_type": "image/jpeg"}), \
         patch("src.api.avatar.storage.generate_quarantine_get", return_value="https://get"), \
         patch("src.api.avatar.check_image", return_value=False), \
         patch("src.api.avatar.storage.copy_to_public") as copy_mock, \
         patch("src.api.avatar.storage.delete_quarantine") as delq_mock:
        resp = _register(client_with_auth, key)
    assert resp.status_code == 422
    copy_mock.assert_not_called()
    delq_mock.assert_called_once_with(key)


def test_register_requires_auth(client_no_auth, test_user):
    resp = client_no_auth.post(
        "/users/me/avatar", json={"object_key": f"users/{test_user.id}/x.jpg"}
    )
    assert resp.status_code == 401


def test_remove_deletes_own_r2_avatar_and_clears(client_with_auth, test_user, db):
    key = f"users/{test_user.id}/old.jpg"
    test_user.avatar_url = f"https://cdn.example.com/{key}"
    db.commit()

    with patch("src.api.avatar.R2_PUBLIC_URL", "https://cdn.example.com"), \
         patch("src.api.avatar.storage.delete_public") as delp_mock:
        resp = client_with_auth.delete("/users/me/avatar")
    assert resp.status_code == 200
    assert resp.json()["avatar_url"] is None
    delp_mock.assert_called_once_with(key)

    db.refresh(test_user)
    assert test_user.avatar_url is None


def test_remove_oauth_avatar_no_delete_call(client_with_auth, test_user, db):
    test_user.avatar_url = "https://lh3.googleusercontent.com/a/old-google-avatar.jpg"
    db.commit()

    with patch("src.api.avatar.R2_PUBLIC_URL", "https://cdn.example.com"), \
         patch("src.api.avatar.storage.delete_public") as delp_mock:
        resp = client_with_auth.delete("/users/me/avatar")
    assert resp.status_code == 200
    assert resp.json()["avatar_url"] is None
    delp_mock.assert_not_called()


def test_remove_when_no_avatar_is_noop(client_with_auth, test_user):
    assert test_user.avatar_url is None
    with patch("src.api.avatar.storage.delete_public") as delp_mock:
        resp = client_with_auth.delete("/users/me/avatar")
    assert resp.status_code == 200
    assert resp.json()["avatar_url"] is None
    delp_mock.assert_not_called()


def test_remove_requires_auth(client_no_auth):
    resp = client_no_auth.delete("/users/me/avatar")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `DATABASE_URL="sqlite:///./test.db" python -m pytest tests/api/users/test_avatar.py -v`
Expected: FAIL — routes 404 / `src.api.avatar` import errors.

- [ ] **Step 3: Write the avatar router**

Create `src/api/avatar.py`:

```python
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.users import get_current_active_user
from src.db.database import get_db
from src.db.tables import User
from src.models.user_models.avatar import (
    AvatarUploadUrlRequest,
    AvatarUploadUrlResponse,
    AvatarRegisterRequest,
)
from src.models.user_models.user import UserPrivateRead
from src.services import storage
from src.services.moderation import check_image
from src.utils.config import R2_PUBLIC_URL

router = APIRouter()

MAX_AVATAR_BYTES = 5 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
EXT_MAP = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def auth_required():
    return Depends(get_current_active_user)


def _delete_if_ours(avatar_url: str | None) -> None:
    if avatar_url and R2_PUBLIC_URL and avatar_url.startswith(R2_PUBLIC_URL):
        old_key = avatar_url[len(R2_PUBLIC_URL) + 1:]
        storage.delete_public(old_key)


@router.post("/me/avatar/upload-url", response_model=AvatarUploadUrlResponse)
def create_avatar_upload_url(
    request: AvatarUploadUrlRequest,
    current_user: User = auth_required(),
):
    if request.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported image type")

    ext = EXT_MAP[request.content_type]
    object_key = f"users/{current_user.id}/{uuid.uuid4().hex}.{ext}"
    upload_url = storage.generate_quarantine_put(object_key, request.content_type)
    return AvatarUploadUrlResponse(upload_url=upload_url, object_key=object_key)


@router.post("/me/avatar", response_model=UserPrivateRead)
def register_avatar(
    request: AvatarRegisterRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: User = auth_required(),
):
    object_key = request.object_key

    if not object_key.startswith(f"users/{current_user.id}/"):
        raise HTTPException(status_code=422, detail="Invalid object key")

    info = storage.head_quarantine(object_key)
    if info is None:
        raise HTTPException(status_code=422, detail="Upload not found")
    if info["size"] > MAX_AVATAR_BYTES:
        storage.delete_quarantine(object_key)
        raise HTTPException(status_code=422, detail="Photo too large (max 5MB)")

    get_url = storage.generate_quarantine_get(object_key)
    if not check_image(get_url):
        storage.delete_quarantine(object_key)
        raise HTTPException(status_code=422, detail="Image violates community guidelines.")

    storage.copy_to_public(object_key)
    storage.delete_quarantine(object_key)

    _delete_if_ours(current_user.avatar_url)

    current_user.avatar_url = storage.public_url_for(object_key)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.delete("/me/avatar", response_model=UserPrivateRead)
def remove_avatar(
    db: Annotated[Session, Depends(get_db)],
    current_user: User = auth_required(),
):
    _delete_if_ours(current_user.avatar_url)
    current_user.avatar_url = None
    db.commit()
    db.refresh(current_user)
    return current_user
```

- [ ] **Step 4: Register the router**

In `src/main.py`, add `avatar` to the `src.api` import line (line 12):

```python
from src.api import users, games, auth, favourites, metadata, optimisation, search, achievements, aliases, comments, feedback, short_links, photos, push_tokens, admin_notifications, avatar
```

Then add, alongside the other `app.include_router(...)` calls (near the `photos.router` line):

```python
app.include_router(avatar.router, prefix="/users", tags=["avatar"])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `DATABASE_URL="sqlite:///./test.db" python -m pytest tests/api/users/test_avatar.py -v`
Expected: PASS (all)

- [ ] **Step 6: Full regression + graph update**

Run: `DATABASE_URL="sqlite:///./test.db" python -m pytest tests/ -q`
Expected: PASS (no regressions across the whole suite — this also re-confirms Tasks 2 and 3's changes didn't break anything elsewhere).

Run: `graphify update .`

- [ ] **Step 7: Commit**

```bash
git add src/api/avatar.py src/main.py tests/api/users/test_avatar.py
git commit -m "$(cat <<'EOF'
feat(avatar): add profile picture upload/register/remove endpoints

POST /users/me/avatar/upload-url, POST /users/me/avatar, and
DELETE /users/me/avatar let a user upload, replace, and remove their
own avatar through the same presigned-R2 + fail-closed moderation
pipeline already used for game photos. Replacing or removing an
avatar cleans up the old R2 object only when it was one we uploaded
(never a provider-hosted OAuth avatar URL).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage:**
- `POST /users/me/avatar/upload-url` (content-type validation, no cap check) → Task 4. ✓
- `POST /users/me/avatar` (prefix check, head/size, moderation, copy+delete, old-avatar cleanup, set avatar_url) → Task 4. ✓
- `DELETE /users/me/avatar` (cleanup + clear) → Task 4. ✓
- Reuse `storage.py` / `check_image` unchanged → Task 4 imports only, no edits to either file. ✓
- Close `UserUpdate.avatar_url` PATCH bypass → Task 2. ✓
- Stop OAuth signup auto-setting `avatar_url` (web + mobile; Apple untouched) → Task 3. ✓
- `AvatarUploadUrlRequest/Response` → Task 1. `AvatarRegisterRequest` — the spec's Pydantic Models section only listed the first two; the register endpoint needs a request body model too (the spec's own endpoint description in "Step 3 — register" shows `{ "object_key": ... }` as the body). Added `AvatarRegisterRequest` in Task 1, mirroring `PhotoRegisterRequest`'s exact shape — this fills a gap in the spec, not a deviation from its intent.
- "our vs OAuth avatar" distinguishing logic → `_delete_if_ours` in Task 4, with an added `R2_PUBLIC_URL` truthiness guard beyond the spec's literal pseudocode: `R2_PUBLIC_URL` defaults to `""` when unset (e.g. in dev/test without R2 configured), and `"".startswith("")` — any string starts with the empty string — would make every avatar look "ours" and trigger spurious `delete_public` calls. Guarding on `R2_PUBLIC_URL` being non-empty as well closes that.
- Frontend integration flow → matches the three endpoints exactly; no backend task needed beyond what's built.
- Test matrix (upload-url happy/bad-type/no-auth, register happy/replace-own/replace-oauth/prefix/missing/oversized/moderation-reject/no-auth, remove happy/oauth/noop/no-auth, PATCH bypass regression, OAuth signup regression) → Tasks 2, 3, 4. ✓

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `storage.*` function names match `src/services/storage.py`'s real signatures (`generate_quarantine_put/get`, `head_quarantine`, `copy_to_public`, `delete_quarantine`, `delete_public`, `public_url_for`) — verified against the actual file, not the spec's paraphrase. `check_image(image_url: str) -> bool` matches `src/services/moderation.py`. `AvatarUploadUrlRequest/Response`, `AvatarRegisterRequest` used identically across Tasks 1 and 4. `UserPrivateRead` (existing model, unchanged) used as the response model for both register and remove, matching what `src/api/users.py` already returns elsewhere.

**Cross-task ordering:** Tasks 2 and 3 are independent of Task 4 and of each other (different files, no shared interfaces) — they could be reordered or done in parallel. Task 4 depends only on Task 1. Task 4's Step 6 runs the *entire* test suite specifically to catch any interaction between Tasks 2/3/4 (e.g. a stray test elsewhere asserting the old `PATCH avatar_url` or OAuth-picture behavior) that wasn't already covered by each task's own regression step.
