# Profile Picture Upload — Design Spec

**Date:** 2026-07-23
**Branch:** `feature/pre-launch-features`
**Status:** Approved design, pre-implementation

## Purpose

Let a user upload, replace, and remove their own profile picture, moderated the same way as
game photos, instead of the current situation where `User.avatar_url` is either set opaquely by
Google OAuth or (until this ships) directly PATCH-able to any `https://` URL with no moderation
at all.

## Scope

**In scope**
- `POST /users/me/avatar/upload-url` — presigned direct-to-R2 upload into the existing
  quarantine bucket.
- `POST /users/me/avatar` — register: validate, moderate (fail-closed), copy to public bucket,
  set `User.avatar_url`, clean up the previous avatar if it was one of ours.
- `DELETE /users/me/avatar` — clear `avatar_url` to `None`, clean up the R2 object if it was
  one of ours.
- Reuse `src/services/storage.py` and `src/services/moderation.check_image` from the Photos
  feature as-is — no changes to either module.
- Close the unmoderated bypass: remove `avatar_url` from `UserUpdate`
  (`src/models/user_models/user.py`) so `PATCH /users/me` can no longer set it directly.

**Out of scope (YAGNI)**
- Cropping / resizing server-side — client crops/compresses before upload, same as Photos.
- A gallery of past avatars — single slot per user, replace-only.
- Admin moderation override / review queue — synchronous fail-closed moderation only, same as
  Photos.
- Changing how OAuth sets `avatar_url` (`src/api/auth.py:357,550`) — untouched; those write to
  the `User` object directly, not through `UserUpdate`.

## Architecture

### Object key scheme

`users/{user_id}/{uuid4hex}.{ext}`, same bucket pair and `ext` derivation
(`image/jpeg`→`jpg`, `image/png`→`png`, `image/webp`→`webp`) as Photos. One live object per
user; the old object is deleted on replace/remove.

### Distinguishing "our" avatars from OAuth avatars

`User.avatar_url` can currently hold a Google-hosted URL (OAuth) or, after this ships, an
`R2_PUBLIC_URL`-prefixed URL (our upload). Before deleting an old avatar object from R2, check:

```python
if current_user.avatar_url and current_user.avatar_url.startswith(R2_PUBLIC_URL):
    old_key = current_user.avatar_url[len(R2_PUBLIC_URL) + 1:]
    storage.delete_public(old_key)
```

If the old `avatar_url` doesn't start with `R2_PUBLIC_URL` (Google URL, or `None`), skip
deletion — it isn't our object to delete.

### Endpoints (new module `src/api/avatar.py`, router mounted at `/users`)

**Step 1 — request a presigned URL**

```
POST /users/me/avatar/upload-url    (auth required)
Body: { "content_type": "image/jpeg" }
```
Validations: `content_type` in {`image/jpeg`, `image/png`, `image/webp`} (422). No cap check —
single slot, always replaces.

Response:
```json
{ "upload_url": "https://<r2-quarantine-presigned-put-url>", "object_key": "users/<user_id>/<uuid>.jpg" }
```

**Step 2 — client PUTs bytes directly to `upload_url`.** Client compresses and enforces the
5 MB cap before upload, same as Photos.

**Step 3 — register**

```
POST /users/me/avatar    (auth required)
Body: { "object_key": "users/<user_id>/<uuid>.jpg" }
```
Logic:
1. `object_key` must belong to this user's prefix `users/{user_id}/` (422 otherwise) —
   prevents registering someone else's object.
2. `storage.head_quarantine(object_key)` — must exist (422 "upload not found"), size ≤ 5 MB
   (422 "photo too large").
3. `check_image(storage.generate_quarantine_get(object_key))` — `False` →
   `storage.delete_quarantine(object_key)`, 422 ("Image violates community guidelines.").
4. On pass: `storage.copy_to_public(object_key)`, `storage.delete_quarantine(object_key)`.
5. If old `avatar_url` is ours (see above), `storage.delete_public(old_key)`.
6. Set `current_user.avatar_url = storage.public_url_for(object_key)`, commit.
7. Return `UserPrivateRead`.

**Remove**

```
DELETE /users/me/avatar    (auth required) → 200, UserPrivateRead
```
- If current `avatar_url` is ours, `storage.delete_public(old_key)`.
- Set `avatar_url = None`, commit, return `UserPrivateRead`.

### Closing the PATCH bypass

Remove `avatar_url: Optional[str] = None` and its `@field_validator('avatar_url')` from
`UserUpdate` (`src/models/user_models/user.py`). No change needed in
`update_my_profile` (`src/api/users.py:214-265`) — its `update_data.items()` /
`setattr` loop simply won't see the field once it's gone from the model. `UserPrivateRead`
(which still has `avatar_url`) is unaffected — reads keep working.

## Pydantic models

Add to `src/models/user_models/user.py` (or a new `avatar.py` alongside `game_photo.py` — either
is fine, `user.py` is small enough to hold these):

- `AvatarUploadUrlRequest` — `content_type: str`
- `AvatarUploadUrlResponse` — `upload_url: str`, `object_key: str`

No dedicated read model — register/remove both return the existing `UserPrivateRead`.

## Frontend Integration

**Upload (profile settings):**
1. User picks an image. FE compresses client-side, enforces 5 MB cap.
2. `POST /users/me/avatar/upload-url` with `content_type` → `upload_url` + `object_key`.
3. `PUT` bytes to `upload_url` with matching `Content-Type` header.
4. `POST /users/me/avatar` with `{ object_key }`. On 200, use the returned `avatar_url` from
   the `UserPrivateRead` body to update the displayed avatar. On 422, show the error (too
   large / moderation reject) and keep the old avatar.

**Remove:** `DELETE /users/me/avatar` → clear avatar in UI (falls back to default/initials).

**Auth/errors:** all three endpoints require auth (401). Bad content-type → 422. Moderation
reject / oversized / missing upload → 422.

**Breaking change for existing clients:** any FE code currently PATCHing `avatar_url` via
`PATCH /users/me` must switch to this flow — that field will start being silently ignored
(FastAPI/Pydantic drops unknown-to-model fields; not an error, just a no-op).

## Testing

Mock `storage` and `check_image`, same as Photos tests — no live R2/OpenAI.

- `upload-url`: happy path returns `upload_url` + `object_key`; bad content_type → 422;
  no auth → 401.
- `register`: happy path copies to public, deletes quarantine, sets `avatar_url`; replacing an
  existing our-R2 avatar deletes the old object; replacing an OAuth (Google) avatar does **not**
  call `delete_public`; key-prefix mismatch → 422; missing quarantine object → 422; oversized →
  422; moderation reject → quarantine deleted, no public copy, 422; no auth → 401.
- `remove`: clears `avatar_url`; deletes our-R2 object if present; no-op delete call when avatar
  was an OAuth URL or already `None`; no auth → 401.
- `PATCH /users/me` with `avatar_url` in the body no longer changes `User.avatar_url` (field
  silently dropped).

Follow existing test setup (SQLite `test.db`, `client_with_auth`). Run with
`DATABASE_URL="sqlite:///./test.db"`.

## Deployment notes

No new env vars or infra — reuses the R2 buckets, `R2_*` config, and `boto3` dependency already
provisioned for Photos. No new table (`avatar_url` already exists on `User`).

## Open questions / future work

- None — this is a small, fully-scoped extension of the already-approved Photos infra.
