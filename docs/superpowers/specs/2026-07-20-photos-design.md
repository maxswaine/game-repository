# Photos (Game Photo Gallery) — Design Spec

**Date:** 2026-07-20
**Branch:** `feature/pre-launch-features`
**Status:** Approved design, pending reviewer pass, pre-implementation

## Purpose

Let users attach photos to a game during the create / rule-setup flow. Each game has a
**gallery** of photos. The first photo (position 0) is the **cover**, shown as the game
card thumbnail. Photos are uploaded directly to Cloudflare R2 via presigned URLs, moderated
on registration, and served from a public CDN URL.

This is the app's first real file-upload system — today `Game.image_url` is just a
client-supplied string with no storage behind it.

## Scope

**In scope**
- `GamePhoto` table: a game-level gallery, cascade-deleted with the game.
- Presigned direct-to-R2 upload into a **private quarantine bucket** (client uploads bytes;
  backend never proxies files).
- Automated image moderation on register (OpenAI omni-moderation), **fail-closed**; only
  moderated images are copied to the public bucket, so a public URL never exists before the
  image passes.
- Cover = photo at `position 0`; reorder endpoint controls order/cover.
- `Game.image_url` kept in sync with the cover photo's public URL for backward compatibility.
- Per-game cap of **10** photos; **5 MB** per photo; content types jpeg/png/webp.

**Out of scope (YAGNI)**
- Per-rule / per-field photo anchoring — gallery is game-level only.
- Image transformations / thumbnails / resizing server-side — client compresses before upload;
  the CDN serves the stored object as-is.
- Non-OpenAI moderators — moderator sits behind a swappable interface so AWS Rekognition can
  be added later without touching the photo system, but only OpenAI ships for launch.
- Admin review queue / pending state — moderation is synchronous at register.
- Captions / alt text on photos — may be a v2 field.

## Prerequisites (user-provisioned infrastructure)

Before this ships to Railway, the user must provision and set env vars:

- **Two** Cloudflare R2 buckets:
  - a **private quarantine bucket** (no public access) — receives raw uploads pre-moderation.
  - a **public bucket** (served via a Cloudflare CDN / custom domain) — holds only moderated,
    approved images.
- A **lifecycle rule** on the quarantine bucket expiring objects after **24 hours**, so uploads
  that are never registered (or fail moderation before delete) self-clean.
- An R2 **API token** (S3-compatible access key + secret) with access to both buckets.
- A **public base URL** for the public bucket — **must be a Cloudflare custom domain**, not
  the `r2.dev` "Public Development URL". `r2.dev` is Cloudflare's explicitly non-production,
  rate-limited dev domain (per Cloudflare docs) and was observed in testing to take up to
  ~60-100s for a freshly-copied object to become servable — unacceptable latency for a photo
  that a register call just approved. A custom domain (your domain added as a Cloudflare zone,
  connected to the bucket) gets Cloudflare Cache in front and does not have this lag.

New environment variables (loaded via `src/utils/config.py` from `.env`):

| Var | Purpose |
|---|---|
| `R2_ACCOUNT_ID` | Cloudflare account id (for the S3 endpoint host) |
| `R2_ACCESS_KEY_ID` | R2 token access key |
| `R2_SECRET_ACCESS_KEY` | R2 token secret |
| `R2_BUCKET` | Public bucket name (moderated images) |
| `R2_QUARANTINE_BUCKET` | Private bucket name (raw pre-moderation uploads) |
| `R2_PUBLIC_URL` | Public base URL, e.g. `https://cdn.whatsthatgame.co.uk` (no trailing slash) |

Why two buckets: an R2 bucket exposed via r2.dev / a custom domain is public **in its
entirety** — there is no native per-prefix public/private split. A separate private bucket is
the clean way to keep unmoderated bytes off the public CDN.

New Python dependency: **`boto3`** (R2 is S3-compatible; use the S3 client against the R2
endpoint `https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com`).

## Architecture

### Data model — `GamePhoto` (in `src/db/tables.py`)

| Column | Type | Notes |
|---|---|---|
| `id` | String (UUID) | Primary key |
| `game_id` | String FK → `games.id` | Indexed; `ondelete="CASCADE"` |
| `object_key` | String | R2 object key; random/unguessable (uuid4-based) |
| `public_url` | String | Full CDN URL served to clients |
| `position` | Integer | 0-based order; `0` = cover |
| `created_at` | DateTime(tz) | |

- Relationship on `Game`: `photos = relationship("GamePhoto", cascade="all, delete-orphan")`,
  ordered by `position`.
- `Game.image_url` is retained and kept in sync: after any photo mutation it is set to the
  cover (position 0) photo's `public_url`, or `None` when the gallery is empty.

### Object key scheme

The same relative key `games/{game_id}/{uuid4hex}.{ext}` is used in **both** buckets — the raw
upload lives at that key in the quarantine bucket, and on approval the identical key is copied
into the public bucket. `ext` derives from the declared content type (`image/jpeg`→`jpg`,
`image/png`→`png`, `image/webp`→`webp`). The random uuid component keeps keys unguessable.

The client is only ever handed a **presigned PUT** to the quarantine bucket — never a public
URL. The public URL is minted by the backend only after moderation passes and the object is in
the public bucket.

### Storage service — `src/services/storage.py`

A thin wrapper around a boto3 S3 client configured for R2. Constructed lazily (like the
OpenAI client) so imports don't require credentials. All quarantine methods target
`R2_QUARANTINE_BUCKET`; public methods target `R2_BUCKET`.

Interface:
- `generate_quarantine_put(object_key: str, content_type: str, expires_in: int = 900) -> str`
  — presigned PUT into the quarantine bucket, 15-minute expiry.
- `generate_quarantine_get(object_key: str, expires_in: int = 300) -> str` — short-lived
  presigned GET into the quarantine bucket, used to hand the image to the moderator.
- `head_quarantine(object_key: str) -> dict | None` — `{"size": int, "content_type": str}` if
  the quarantine object exists, else `None`.
- `copy_to_public(object_key: str) -> None` — server-side copy quarantine→public at the same key.
- `delete_quarantine(object_key: str) -> None` — idempotent delete from quarantine.
- `delete_public(object_key: str) -> None` — idempotent delete from public.
- `public_url_for(object_key: str) -> str` — `f"{R2_PUBLIC_URL}/{object_key}"`.

### Moderation — `src/services/moderation.py` (extended)

Add an image path alongside the existing `check_content(text)`:

- `check_image(image_url: str) -> bool` — calls OpenAI `moderations.create` with
  `model="omni-moderation-2024-09-26"` and multimodal input
  `[{"type": "image_url", "image_url": {"url": image_url}}]`. The `image_url` passed in is a
  **short-lived presigned GET on the quarantine object** (bytes still never traverse Railway;
  OpenAI fetches directly). If OpenAI cannot fetch a presigned URL, fall back to sending the
  bytes as a base64 data URL (backend fetches from quarantine, one small egress). Returns
  `True` (safe) only if none of `sexual`, `sexual/minors`, `violence/graphic`, `hate`,
  `hate/threatening` are flagged.
- **Fail-closed:** on any exception, return `False` (reject). This differs from `check_content`,
  which fails open (returns `True`) — images are higher risk on a public catalogue.
- Wrapped behind a module-level indirection (`get_image_moderator()` returning a callable /
  small class) so a different provider can be swapped in without changing call sites.

### Upload / register flow

**Step 1 — request a presigned URL**

```
POST /games/{game_id}/photos/upload-url    (auth required, owner only)
Body: { "content_type": "image/jpeg" }
```
Validations:
- Game exists (404) and is owned by the caller (403).
- Current photo count for the game < 10 (409 with a clear message).
- `content_type` in {`image/jpeg`, `image/png`, `image/webp`} (422).

Response (note: **no** public URL — nothing is public yet):
```json
{
  "upload_url": "https://<r2-quarantine-presigned-put-url>",
  "object_key": "games/<game_id>/<uuid>.jpg"
}
```

**Step 2 — client PUTs bytes directly to `upload_url`** (quarantine bucket). Client compresses
and enforces the 5 MB cap before upload. Not a backend call.

**Step 3 — register the photo**

```
POST /games/{game_id}/photos    (auth required, owner only)
Body: { "object_key": "games/<game_id>/<uuid>.jpg" }
```
Logic:
1. Game owned by caller (403) else 404.
2. Re-check count < 10 (409) — guards against races / direct calls.
3. `object_key` must belong to this game's prefix `games/{game_id}/` (422 otherwise) — prevents
   registering someone else's object.
4. `storage.head_quarantine(object_key)` — object must exist in quarantine (422 "upload not
   found") and `size` ≤ 5 MB (422 "photo too large").
5. `check_image(storage.generate_quarantine_get(object_key))` — if `False`,
   `storage.delete_quarantine(object_key)` and return 422 ("Image violates community
   guidelines.").
6. On pass: `storage.copy_to_public(object_key)`, then `storage.delete_quarantine(object_key)`.
7. Create `GamePhoto` with `object_key`, `public_url = storage.public_url_for(object_key)`, and
   `position = current_count` (append at end; first photo gets 0 = cover).
8. Resync `Game.image_url` to the cover photo's `public_url`.
9. Return the created `GamePhotoRead`.

**Size cap note:** a presigned **PUT** cannot constrain body size, so the 5 MB cap is enforced
**after** upload via `head_quarantine` (step 4) — an oversized object lands in quarantine, is
rejected at register, deleted, and would self-expire via the 24h lifecycle rule regardless.
Optionally use a presigned **POST** with a `content-length-range` condition to reject oversized
bodies at upload time *if R2 supports POST policies* (its S3 compatibility here is partial —
implementer should verify; if unsupported, the post-upload `head` check is the enforcement).

**Delete**

```
DELETE /games/{game_id}/photos/{photo_id}    (auth required, owner only) → 204
```
- Owner check (403), photo belongs to game (404).
- `storage.delete_public(object_key)`, delete the row.
- Re-pack `position` values so they stay contiguous (0..n-1), preserving order.
- Resync `Game.image_url` to the new cover (or `None` if the gallery is now empty).

**Reorder / set cover**

```
PATCH /games/{game_id}/photos/order    (auth required, owner only)
Body: { "photo_ids": ["<id>", "<id>", ...] }
```
- Owner check (403).
- `photo_ids` must be exactly the set of the game's current photo ids (422 otherwise).
- Assign `position` by list index; index 0 becomes the cover.
- Resync `Game.image_url` to the new cover.
- Return the reordered `list[GamePhotoRead]`.

### Read path

`GameRead` gains `photos: list[GamePhotoRead]`, ordered by `position`. Populated in
`map_game_to_read`. No separate list endpoint — the gallery ships with the game payload.

`GamePhotoRead`: `{ id: str, public_url: str, position: int }`.

**N+1 guard:** `photos` now loads for every game in list endpoints (`GET /games/`,
`GET /games/mine`) and search. Add `selectinload(Game.photos)` to those queries — the same
fan-out treatment `equipment_items` / `setting_items` / `alias_objects` already get — so a
20-item page does not fire 20 extra photo queries.

### `image_url` reconciliation

`POST /games/` still accepts a client-supplied `image_url` and stores it as-is (unchanged, for
backward compatibility with the existing create flow). The cover-sync logic only **overwrites**
`image_url` once the game has at least one `GamePhoto` (on register/delete/reorder). A game with
no photos keeps whatever `image_url` the client sent; a game with photos always has
`image_url` == the cover's `public_url`. Cover-sync sets `image_url = None` only when the last
photo is deleted *and* the gallery was the source of the current value — in practice, once
photos exist they own `image_url`.

## Pydantic models (`src/models/game_models/game_photo.py`)

- `PhotoUploadUrlRequest` — `content_type: str`
- `PhotoUploadUrlResponse` — `upload_url: str`, `object_key: str` (no public URL — the object
  is not public until it passes moderation at register)
- `PhotoRegisterRequest` — `object_key: str`
- `PhotoReorderRequest` — `photo_ids: list[str]`
- `GamePhotoRead` — `id: str`, `public_url: str`, `position: int`

## Frontend Integration

**Upload (setup flow):**
1. User selects/takes a photo. FE compresses client-side and enforces the 5 MB cap.
2. `POST /games/{id}/photos/upload-url` with the file's `content_type` → get `upload_url` +
   `object_key`. (No public URL is returned — the photo is not public yet.)
3. `PUT` the (compressed) bytes to `upload_url` with the matching `Content-Type` header.
   Show per-photo progress. This uploads to the private quarantine bucket.
4. `POST /games/{id}/photos` with `{ object_key }`. On 200, use the returned `public_url` to
   render the photo in the gallery UI. On 422, show the error and drop the photo (moderation
   reject or too-large). The `public_url` only exists after this call succeeds.
5. Enforce the 10-photo cap in the UI; the backend also returns 409 past the cap.

**Ordering:** drag-to-reorder → `PATCH /games/{id}/photos/order` with the full ordered
`photo_ids`. Position 0 is the cover.

**Delete:** `DELETE /games/{id}/photos/{photo_id}` → remove from UI on 204.

**Display:**
- Game card thumbnail: use existing `GameRead.image_url` (auto-synced to the cover) — no FE
  change needed for cards.
- Game detail: render `GameRead.photos[]` as a gallery in `position` order.

**Auth/errors:** all photo write endpoints require auth (401) and owner (403). Content-type
not allowed → 422. Cap exceeded → 409.

## Testing

Mock the storage service (presign/head/copy/delete) and moderation — no live R2 or OpenAI in
tests.

- `upload-url`: happy path returns `upload_url` + `object_key` (no public_url); bad content_type
  → 422; non-owner → 403; at 10 photos → 409; missing game → 404.
- `register`: happy path copies to public, deletes quarantine, creates row, first photo becomes
  cover and syncs `image_url`; key-prefix mismatch → 422; object missing (`head_quarantine`
  None) → 422; oversized (`head_quarantine` size > 5 MB) → 422; moderation reject → quarantine
  object deleted, **no** public copy, 422; count race at 10 → 409; non-owner → 403.
- `delete`: removes row + calls `storage.delete_public`; re-packs positions; resyncs cover;
  empties `image_url` when last photo removed; non-owner → 403.
- `reorder`: reassigns positions by index; new cover syncs `image_url`; wrong id set → 422;
  non-owner → 403.
- `GameRead.photos` present and ordered by position on `GET /games/{id}`.
- `check_image`: safe image → True; flagged category → False; exception → False (fail-closed).

Follow existing test setup (SQLite `test.db`, `client_with_auth`, `client_as_second_user`,
`client_no_auth`, game helpers). Run with `DATABASE_URL="sqlite:///./test.db"`.

## Deployment notes

- `GamePhoto` table auto-creates on Railway via `Base.metadata.create_all` (no Alembic) — same
  as other tables. See the Railway hosting notes.
- Set the six `R2_*` env vars in Railway before/at deploy. Without them, photo endpoints will
  error at first use (storage client construction) — acceptable, but provision first.
- Provision **both** buckets and the quarantine **24h lifecycle rule** before deploy. The public
  bucket needs its CDN/custom domain wired to `R2_PUBLIC_URL`; the quarantine bucket must **not**
  be publicly accessible.
- `boto3` must be added to `requirements.txt`.

## Cost

Per `docs/ai-photo-cost-analysis.md`: sub-cent per game (R2 storage/ops inside free tier for a
long time; OpenAI moderation is free). Photo bytes never traverse Railway (presigned direct
upload + CDN serve), so Railway egress stays negligible.

## Open questions / future work

- Captions / alt text (accessibility) — deferred to v2.
- Server-side thumbnail generation if card performance needs smaller images — deferred; client
  compression is enough for launch.
- Swap or add AWS Rekognition behind the `ImageModerator` interface if OpenAI image retention
  becomes a concern.
