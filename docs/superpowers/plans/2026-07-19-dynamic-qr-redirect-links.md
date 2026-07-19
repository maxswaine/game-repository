# Dynamic QR Redirect Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build owner-controlled dynamic QR links — a fixed `/qr/{code}` endpoint that 302-redirects to an editable `target_url`, managed by admin endpoints.

**Architecture:** One new `short_links` table maps a permanent `code` to a mutable `target_url`. A public router serves the redirect; an admin router (gated by `require_admin`) manages the rows. QR images are made externally and are out of scope. Follows the existing `src/api/aliases.py` two-router pattern.

**Tech Stack:** FastAPI, SQLAlchemy (Column-style ORM in `src/db/tables.py`), Pydantic v2 (`field_validator`, `ConfigDict`), pytest with SQLite + transaction rollback.

## Global Constraints

- Pydantic v2 only — use `field_validator` + `@classmethod` and `ConfigDict(from_attributes=True)`, matching `src/models/alias_models/alias.py`.
- No Alembic. New table is auto-created by `Base.metadata.create_all` on startup (`src/main.py:46`) and on Railway deploy. No migration step.
- Redirect status code MUST be **302** (never 301) so target changes stay live.
- Admin endpoints use the `require_admin` dependency from `src/api/users.py`; public redirect takes no auth.
- `target_url` must start with `http://` or `https://`. `code` must match `^[a-zA-Z0-9_-]+$`.
- Tests follow the existing pattern: `client_no_auth`, `client_as_admin`, and `db` fixtures from `tests/conftest.py`; each test rolls back.
- End every commit message with the two trailers:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_0124jB12JdamqoFv59wd5jed`.

## File Structure

- Create `src/models/short_link_models/__init__.py` — package marker.
- Create `src/models/short_link_models/short_link.py` — `ShortLinkCreate`, `ShortLinkPatch`, `ShortLinkRead`.
- Modify `src/db/tables.py` — add `ShortLink` table.
- Create `src/api/short_links.py` — `public_router` (redirect) + `admin_router` (management).
- Modify `src/main.py` — register both routers.
- Create `tests/api/short_links/__init__.py` — package marker.
- Create `tests/api/short_links/test_short_links.py` — redirect + admin tests.

---

### Task 1: Data layer — table and Pydantic models

**Files:**
- Modify: `src/db/tables.py` (add class after `Feedback`, end of file)
- Create: `src/models/short_link_models/__init__.py`
- Create: `src/models/short_link_models/short_link.py`
- Test: `tests/api/short_links/__init__.py`, `tests/api/short_links/test_short_links.py`

**Interfaces:**
- Produces: SQLAlchemy model `ShortLink` with columns `code` (str, PK), `target_url` (str), `label` (str|None), `is_active` (bool), `scan_count` (int), `created_at`, `updated_at`.
- Produces: `ShortLinkCreate(code: str, target_url: str, label: str | None = None)`, `ShortLinkPatch(target_url: str | None, label: str | None, is_active: bool | None)`, `ShortLinkRead` (all fields, `from_attributes=True`).

- [ ] **Step 1: Write the failing test**

Create `tests/api/short_links/__init__.py` (empty file).

Create `tests/api/short_links/test_short_links.py`:

```python
import pytest


def test_create_short_link_model_validates_code_and_url():
    from src.models.short_link_models.short_link import ShortLinkCreate

    ok = ShortLinkCreate(code="poster1", target_url="https://example.com/dl")
    assert ok.code == "poster1"
    assert ok.label is None

    with pytest.raises(ValueError):
        ShortLinkCreate(code="bad code!", target_url="https://example.com")

    with pytest.raises(ValueError):
        ShortLinkCreate(code="poster1", target_url="ftp://example.com")


def test_short_link_table_row_roundtrips(db):
    from src.db.tables import ShortLink

    row = ShortLink(code="poster1", target_url="https://example.com/dl")
    db.add(row)
    db.commit()
    db.refresh(row)

    assert row.is_active is True
    assert row.scan_count == 0
    assert row.created_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/short_links/test_short_links.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.models.short_link_models'` / cannot import `ShortLink`.

- [ ] **Step 3: Add the `ShortLink` table**

Append to `src/db/tables.py` (uses `datetime`, `timezone`, `Column`, `String`, `Boolean`, `Integer`, `DateTime` already imported at top of file):

```python
class ShortLink(Base):
    __tablename__ = "short_links"
    code = Column(String, primary_key=True)
    target_url = Column(String, nullable=False)
    label = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    scan_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
```

- [ ] **Step 4: Create the Pydantic models**

Create `src/models/short_link_models/__init__.py` (empty file).

Create `src/models/short_link_models/short_link.py`:

```python
import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

CODE_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_target_url(value: str) -> str:
    if not value.startswith(("http://", "https://")):
        raise ValueError("target_url must start with http:// or https://")
    return value


class ShortLinkCreate(BaseModel):
    code: str
    target_url: str
    label: Optional[str] = None

    @field_validator("code")
    @classmethod
    def code_url_safe(cls, value: str) -> str:
        if not CODE_PATTERN.match(value):
            raise ValueError("code must match ^[a-zA-Z0-9_-]+$")
        return value

    @field_validator("target_url")
    @classmethod
    def target_url_scheme(cls, value: str) -> str:
        return _validate_target_url(value)


class ShortLinkPatch(BaseModel):
    target_url: Optional[str] = None
    label: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("target_url")
    @classmethod
    def target_url_scheme(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_target_url(value)


class ShortLinkRead(BaseModel):
    code: str
    target_url: str
    label: Optional[str] = None
    is_active: bool
    scan_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/api/short_links/test_short_links.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add src/db/tables.py src/models/short_link_models/ tests/api/short_links/
git commit -m "feat(qr): add short_links table and pydantic models

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0124jB12JdamqoFv59wd5jed"
```

---

### Task 2: Public redirect endpoint

**Files:**
- Create: `src/api/short_links.py`
- Modify: `src/main.py` (import + register `public_router`)
- Test: `tests/api/short_links/test_short_links.py` (append)

**Interfaces:**
- Consumes: `ShortLink` table (Task 1).
- Produces: module `src/api/short_links.py` exposing `public_router` with `GET /qr/{code}`. Returns 302 with `Location: target_url` for an active code; 404 for missing or inactive; increments `scan_count`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/short_links/test_short_links.py`:

```python
def _seed_link(db, code="poster1", target="https://example.com/dl", active=True):
    from src.db.tables import ShortLink
    row = ShortLink(code=code, target_url=target, is_active=active)
    db.add(row)
    db.commit()
    return row


def test_redirect_active_code_returns_302(client_no_auth, db):
    _seed_link(db)
    response = client_no_auth.get("/qr/poster1", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/dl"


def test_redirect_increments_scan_count(client_no_auth, db):
    from src.db.tables import ShortLink
    _seed_link(db)
    client_no_auth.get("/qr/poster1", follow_redirects=False)
    client_no_auth.get("/qr/poster1", follow_redirects=False)
    row = db.query(ShortLink).filter(ShortLink.code == "poster1").first()
    assert row.scan_count == 2


def test_redirect_inactive_code_returns_404(client_no_auth, db):
    _seed_link(db, code="dead", active=False)
    response = client_no_auth.get("/qr/dead", follow_redirects=False)
    assert response.status_code == 404


def test_redirect_missing_code_returns_404(client_no_auth):
    response = client_no_auth.get("/qr/nonexistent", follow_redirects=False)
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/short_links/test_short_links.py -k redirect -v`
Expected: FAIL — 404 route not found for `/qr/...` (router not registered yet), so 302 assertions fail.

- [ ] **Step 3: Create the router module with the redirect endpoint**

Create `src/api/short_links.py`:

```python
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from src.api.users import require_admin
from src.db.database import get_db
from src.db.tables import ShortLink
from src.models.short_link_models.short_link import (
    ShortLinkCreate,
    ShortLinkPatch,
    ShortLinkRead,
)

public_router = APIRouter()
admin_router = APIRouter()


@public_router.get("/qr/{code}")
def redirect_short_link(code: str, db: Session = Depends(get_db)):
    link = db.query(ShortLink).filter(ShortLink.code == code).first()
    if not link or not link.is_active:
        raise HTTPException(status_code=404, detail="Link not found")
    link.scan_count += 1
    db.commit()
    return RedirectResponse(link.target_url, status_code=302)
```

- [ ] **Step 4: Register the public router**

In `src/main.py`, add `short_links` to the existing `src.api` import on line 12:

```python
from src.api import users, games, auth, favourites, metadata, optimisation, search, achievements, aliases, comments, feedback, short_links
```

After the last `app.include_router(...)` line (currently `feedback`, line 72), add:

```python
app.include_router(short_links.public_router, prefix="", tags=["short_links"])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/api/short_links/test_short_links.py -k redirect -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add src/api/short_links.py src/main.py tests/api/short_links/test_short_links.py
git commit -m "feat(qr): add public /qr/{code} redirect endpoint

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0124jB12JdamqoFv59wd5jed"
```

---

### Task 3: Admin management endpoints

**Files:**
- Modify: `src/api/short_links.py` (add admin endpoints to existing `admin_router`)
- Modify: `src/main.py` (register `admin_router`)
- Test: `tests/api/short_links/test_short_links.py` (append)

**Interfaces:**
- Consumes: `ShortLink` table, Pydantic models (Task 1), `admin_router` (Task 2).
- Produces on `admin_router` (mounted at `/admin`): `POST /admin/links` (201; 409 on dup), `GET /admin/links` (list), `PATCH /admin/links/{code}` (update target/label/is_active, bump `updated_at`; 404 missing), `DELETE /admin/links/{code}` (204; 404 missing). Validation errors return 422.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/short_links/test_short_links.py`:

```python
def test_admin_create_link_returns_201(client_as_admin):
    response = client_as_admin.post(
        "/admin/links",
        json={"code": "freshers25", "target_url": "https://example.com/dl", "label": "Freshers"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["code"] == "freshers25"
    assert data["scan_count"] == 0
    assert data["is_active"] is True


def test_admin_create_duplicate_code_returns_409(client_as_admin):
    payload = {"code": "dup1", "target_url": "https://example.com"}
    client_as_admin.post("/admin/links", json=payload)
    response = client_as_admin.post("/admin/links", json=payload)
    assert response.status_code == 409


def test_admin_create_bad_url_returns_422(client_as_admin):
    response = client_as_admin.post(
        "/admin/links", json={"code": "x1", "target_url": "notaurl"}
    )
    assert response.status_code == 422


def test_admin_create_bad_code_returns_422(client_as_admin):
    response = client_as_admin.post(
        "/admin/links", json={"code": "bad code!", "target_url": "https://example.com"}
    )
    assert response.status_code == 422


def test_admin_list_links(client_as_admin):
    client_as_admin.post(
        "/admin/links", json={"code": "listme", "target_url": "https://example.com"}
    )
    response = client_as_admin.get("/admin/links")
    assert response.status_code == 200
    assert any(link["code"] == "listme" for link in response.json())


def test_admin_patch_target_url(client_as_admin):
    client_as_admin.post(
        "/admin/links", json={"code": "patch1", "target_url": "https://old.com"}
    )
    response = client_as_admin.patch(
        "/admin/links/patch1", json={"target_url": "https://new.com"}
    )
    assert response.status_code == 200
    assert response.json()["target_url"] == "https://new.com"


def test_admin_patch_deactivate_then_redirect_404(client_as_admin, client_no_auth):
    client_as_admin.post(
        "/admin/links", json={"code": "kill1", "target_url": "https://example.com"}
    )
    client_as_admin.patch("/admin/links/kill1", json={"is_active": False})
    response = client_no_auth.get("/qr/kill1", follow_redirects=False)
    assert response.status_code == 404


def test_admin_patch_missing_returns_404(client_as_admin):
    response = client_as_admin.patch(
        "/admin/links/ghost", json={"target_url": "https://example.com"}
    )
    assert response.status_code == 404


def test_admin_delete_link(client_as_admin, client_no_auth):
    client_as_admin.post(
        "/admin/links", json={"code": "del1", "target_url": "https://example.com"}
    )
    delete = client_as_admin.delete("/admin/links/del1")
    assert delete.status_code == 204
    redirect = client_no_auth.get("/qr/del1", follow_redirects=False)
    assert redirect.status_code == 404


def test_admin_delete_missing_returns_404(client_as_admin):
    response = client_as_admin.delete("/admin/links/ghost")
    assert response.status_code == 404


def test_non_admin_cannot_create_link(client_with_auth):
    response = client_with_auth.post(
        "/admin/links", json={"code": "nope", "target_url": "https://example.com"}
    )
    assert response.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/short_links/test_short_links.py -k admin -v`
Expected: FAIL — `/admin/links` routes return 404 (not registered / not implemented).

- [ ] **Step 3: Add the admin endpoints**

Append to `src/api/short_links.py` (all imports already present from Task 2):

```python
@admin_router.post("/links", response_model=ShortLinkRead, status_code=201)
def create_short_link(
    body: ShortLinkCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    if db.query(ShortLink).filter(ShortLink.code == body.code).first():
        raise HTTPException(status_code=409, detail="Code already exists")
    link = ShortLink(code=body.code, target_url=body.target_url, label=body.label)
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@admin_router.get("/links", response_model=list[ShortLinkRead])
def list_short_links(
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    return db.query(ShortLink).all()


@admin_router.patch("/links/{code}", response_model=ShortLinkRead)
def update_short_link(
    code: str,
    body: ShortLinkPatch,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    link = db.query(ShortLink).filter(ShortLink.code == code).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    if body.target_url is not None:
        link.target_url = body.target_url
    if body.label is not None:
        link.label = body.label
    if body.is_active is not None:
        link.is_active = body.is_active
    link.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(link)
    return link


@admin_router.delete("/links/{code}", status_code=204)
def delete_short_link(
    code: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    link = db.query(ShortLink).filter(ShortLink.code == code).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    db.delete(link)
    db.commit()
```

- [ ] **Step 4: Register the admin router**

In `src/main.py`, after the `public_router` registration line added in Task 2, add:

```python
app.include_router(short_links.admin_router, prefix="/admin", tags=["short_links"])
```

- [ ] **Step 5: Run the full test file to verify all pass**

Run: `pytest tests/api/short_links/test_short_links.py -v`
Expected: PASS (all tests green).

- [ ] **Step 6: Run the whole suite for regressions**

Run: `pytest -q`
Expected: PASS — no existing tests broken.

- [ ] **Step 7: Commit**

```bash
git add src/api/short_links.py src/main.py tests/api/short_links/test_short_links.py
git commit -m "feat(qr): add admin CRUD endpoints for short links

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0124jB12JdamqoFv59wd5jed"
```

---

### Task 4: Clean root slugs on the QR host (amendment)

Added after review: QR URLs should read `qr.whatsthatgame.co.uk/instagram`, not
`.../qr/instagram`. Implemented as a pure-ASGI `QRHostRewrite` middleware (not a second
app, not a root catch-all — both have defects: sub-app breaks `dependency_overrides`, a
root `/{code}` route shadows real routes and can break `/version` on every host).

**Files:**
- Modify: `src/utils/config.py` — add `QR_HOST = os.getenv("QR_HOST", "qr.whatsthatgame.co.uk")`
- Modify: `src/api/short_links.py` — add `QRHostRewrite` ASGI middleware class
- Modify: `src/main.py` — `app.add_middleware(short_links.QRHostRewrite, qr_host=QR_HOST)`
- Test: `tests/api/short_links/test_short_links.py`

**Behaviour:** when `Host == QR_HOST` and path is not `/` and not already `/qr/...`,
rewrite `scope["path"]` to `/qr` + path before routing. Reuses the existing handler.

**Tests added (all passing):**
- qr-host `/instagram` (seeded) → 302 to target
- qr-host `/version` → 404 (API isolated on the QR host)
- non-qr-host `/instagram` → 404 (no root-level leak)
- qr-host `/qr/instagram` → 302 (idempotent rewrite, prefixed form still works)

## Self-Review

**Spec coverage:**
- `short_links` table with all 7 columns → Task 1 ✓
- 302 redirect, invisible → Task 2 ✓
- `is_active` kill switch (404) → Task 2 (inactive) + Task 3 (patch deactivate) ✓
- `scan_count` increment → Task 2 ✓
- `code` vs `label` semantics → Task 1 models ✓
- Admin POST/GET/PATCH/DELETE, 409 dup, 404 missing → Task 3 ✓
- `require_admin` gating, non-admin 403 → Task 3 ✓
- Validation: `target_url` http(s), `code` regex, 422 → Task 1 (validators) + Task 3 (422 tests) ✓
- Wire-up in `main.py` (`/qr` at root, admin at `/admin`) → Task 2 + Task 3 ✓
- No migration (create_all) → Global Constraints ✓
- Out of scope (image gen, frontend, bulk, per-scan analytics) → not built ✓

**Placeholder scan:** none — every code step shows complete code.

**Type consistency:** `ShortLink`, `ShortLinkCreate/Patch/Read`, `public_router`, `admin_router`, field names (`code`, `target_url`, `label`, `is_active`, `scan_count`) consistent across all tasks.
