# Dynamic QR Redirect Links — Design

**Date:** 2026-07-19
**Status:** Approved, ready for implementation plan

## Purpose

Let us print a QR code whose destination we control after printing. The QR image
never changes; we swap where it redirects from a database record. This removes the
dependence on a third-party service (bit.ly, qr-code-generator, etc.) and keeps the
redirect on infrastructure we own.

Scope for this iteration: a small number of hand-managed marketing QR codes (posters,
flyers, business cards) whose targets we edit rarely and by hand. The design scales to
many codes later without rework, but we are not building bulk generation or a frontend
admin UI now.

## Key concepts

- **The QR's own address is frozen at print time.** It encodes
  `https://<api-domain>/qr/{code}` — domain, prefix, and code are permanent, because
  they are baked into the printed image. This is the stable handle, by design.
- **The target is dynamic.** Each code maps to a `target_url` stored in the database.
  Changing that row changes where the QR sends people. The QR image is untouched.
- This is the same model every dynamic-QR service uses; we are being our own bit.ly.
- **Permanence requirement:** the API domain must remain live indefinitely. If it dies,
  every printed QR breaks. This is the same risk third-party services carry, except we
  control the domain.

## QR image generation — out of scope

The backend does **not** generate QR images. For each use case we create the image
externally (any QR tool) pointing at the fixed `https://<api-domain>/qr/{code}` URL,
once. The backend's only jobs are: redirect, and let an admin manage the mapping.

## Redirect behaviour

Redirects use HTTP **302 (temporary)**, never 301. A 301 is cached hard by browsers, so
a later target change would not take effect for anyone who already scanned. 302 keeps the
redirect dynamic. The redirect is invisible to the user — the phone follows it
automatically and shows only the destination page. No intermediate landing page.

## Data model

New table `short_links` in `src/db/tables.py`. Railway's `create_all` on startup
auto-creates it on deploy; no migration needed.

| Column       | Type     | Notes                                                        |
|--------------|----------|-------------------------------------------------------------|
| `code`       | String   | Primary key. The slug in the QR URL, e.g. `freshers25`. Public, URL-safe, unique. |
| `target_url` | String   | Not null. Redirect destination. Editable at any time.       |
| `label`      | String   | Nullable. Private admin note (e.g. "Freshers fair 2025 poster"). Never public, never in the URL — a human memory aid for the admin list. |
| `is_active`  | Boolean  | Not null, default `True`. Kill switch — set `False` to disable a QR (returns 404) without deleting it. |
| `scan_count` | Integer  | Not null, default `0`. Incremented on each successful redirect. |
| `created_at` | DateTime | UTC, set on creation.                                       |
| `updated_at` | DateTime | UTC, bumped whenever the target/label/active state changes. |

### `code` vs `label`

- `code` is the slug embedded in the public QR URL (`/qr/{code}`). Whoever scans hits it.
- `label` is a private note only the admin sees, to identify which physical QR a row is.

## Endpoints

### Public redirect (no auth)

New module `src/api/short_links.py`, `public_router`, mounted at root prefix `""`.

```
GET /qr/{code}
  - look up code
  - if not found OR is_active is False  -> 404
  - increment scan_count, commit
  - return RedirectResponse(target_url, status_code=302)
```

The `/qr` top-level prefix is reserved. It works on every host the API serves.

### Clean root slugs on the QR host (`QRHostRewrite` middleware)

The API is served on a shared FastAPI app across multiple hosts (`api.`, the Railway
domain, and a dedicated `qr.` subdomain). We want QR URLs to read cleanly —
`qr.whatsthatgame.co.uk/instagram`, not `.../qr/instagram` — without a redundant path
segment and without a root-level catch-all that could shadow real API routes.

Solution: a pure-ASGI middleware `QRHostRewrite` in `src/api/short_links.py`. When the
request `Host` equals `QR_HOST` (env var, default `qr.whatsthatgame.co.uk`) and the path
is not `/` and does not already start with `/qr/`, it rewrites `scope["path"]` from
`/instagram` to `/qr/instagram` before routing. The existing `/qr/{code}` handler then
serves it.

Why middleware rather than a second app or a root `/{code}` route:
- Same app → all existing fixtures and `dependency_overrides` keep working.
- Routing table is untouched → cannot shadow `/version`, `/games`, etc.
- Full host isolation: on the QR host, any non-`/qr/` path becomes a short-link lookup,
  so `qr.whatsthatgame.co.uk/version` returns 404 (the API is not exposed there). No
  reserved-slug caveat.

Both forms work: `qr.whatsthatgame.co.uk/instagram` (rewritten) and `.../qr/instagram`
(direct) hit the same handler. The printed QR uses the clean root form.

### Admin management (`require_admin`, mounted at `/admin`)

`admin_router` in the same module, following the existing `aliases.py` admin pattern
(`require_admin` dependency from `src/api/users.py`).

| Endpoint                     | Behaviour                                                        |
|------------------------------|-----------------------------------------------------------------|
| `POST /admin/links`          | Create `{code, target_url, label?}`. 409 if code already exists. |
| `GET /admin/links`           | List all links with scan counts.                                |
| `PATCH /admin/links/{code}`  | Update `target_url`, `label`, and/or `is_active`. Bumps `updated_at`. 404 if missing. |
| `DELETE /admin/links/{code}` | Delete the link. 404 if missing.                                |

Initially driven via FastAPI's auto-generated Swagger UI at `/docs` using an admin
bearer token — no frontend work required. A future frontend admin panel can call the
same endpoints unchanged. The same endpoints also cover a future "many codes" workflow.

## Validation

- `target_url` must start with `http://` or `https://` (reject input that would break the
  redirect).
- `code` must match `^[a-zA-Z0-9_-]+$` (URL-safe; avoids collisions and malformed paths).

## Pydantic models

New folder `src/models/short_link_models/` following the domain-folder convention:

- `ShortLinkCreate` — `code`, `target_url`, optional `label`.
- `ShortLinkPatch` — optional `target_url`, `label`, `is_active`.
- `ShortLinkRead` — full row for admin responses (includes `scan_count`, timestamps).

## Wire-up (`src/main.py`)

```python
from src.api import short_links
app.include_router(short_links.public_router, prefix="", tags=["short_links"])
app.include_router(short_links.admin_router, prefix="/admin", tags=["short_links"])
```

## Testing

Following the existing SQLite/transaction-rollback test setup:

Redirect:
- valid active code -> 302 with correct `Location` target
- inactive code -> 404
- missing code -> 404
- `scan_count` increments on redirect

Admin:
- create link (201); duplicate code -> 409
- patch `target_url` -> persisted, `updated_at` bumped
- patch `is_active` False -> redirect then 404
- delete link -> subsequent redirect 404
- non-admin caller -> 403
- validation: bad `target_url` -> 422; bad `code` -> 422

## Out of scope (YAGNI)

- Backend QR image generation.
- Frontend admin UI.
- Bulk / on-demand code generation.
- Per-scan analytics beyond a total count (no timestamps-per-scan, geo, device).
- Vanity vs random code auto-generation — codes are chosen by the admin at create time.
