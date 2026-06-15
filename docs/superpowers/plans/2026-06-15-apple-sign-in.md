# Sign in with Apple — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `POST /auth/oauth/apple/token` so the iOS app can authenticate via Sign in with Apple and receive a JWT.

**Architecture:** The iOS app sends Apple's `identityToken` (a signed JWT) to the backend. The backend verifies it against Apple's public JWK Set (cached for 24 h), extracts `sub` and `email`, then finds or creates a `User` row with `oauth_provider="apple"`. Returns the same `{access_token, token_type, is_new_user}` shape as the existing Google mobile endpoint.

**Tech Stack:** FastAPI, SQLAlchemy, PyJWT (`import jwt` + `jwt.algorithms.RSAAlgorithm`), httpx (already used for Google OAuth), pytest with `unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-06-15-apple-sign-in-design.md`

---

## File Map

| Action | Path |
|--------|------|
| Modify | `src/api/auth.py` — add JWKS cache, `verify_apple_token`, `AppleTokenRequest`, endpoint |
| Create | `tests/api/auth/test_apple_sign_in.py` |
| No change | `src/db/tables.py` — `oauth_provider`/`oauth_id` columns already exist |
| No change | `src/main.py` — `auth.router` already registered |

---

## Task 1: Add JWKS cache and verify_apple_token to auth.py

**Files:**
- Modify: `src/api/auth.py`

`verify_apple_token` is a thin wrapper around PyJWT + httpx with no custom branching logic.
It is tested indirectly via endpoint tests (Tasks 2–8) which mock it out. Direct unit testing
would require RSA key generation infrastructure for minimal coverage benefit.

- [ ] **Step 1: Add imports to src/api/auth.py**

Add after the existing imports at the top of the file:

```python
import json
from jwt.algorithms import RSAAlgorithm
```

- [ ] **Step 2: Add JWKS cache globals and _get_apple_jwks helper**

Add after the `_exchange_codes` dict (around line 27):

```python
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
_apple_jwks_cache: list[dict] | None = None
_apple_jwks_cache_expires: datetime | None = None


async def _get_apple_jwks() -> list[dict]:
    global _apple_jwks_cache, _apple_jwks_cache_expires
    now = datetime.now(timezone.utc)
    if _apple_jwks_cache is not None and _apple_jwks_cache_expires and now < _apple_jwks_cache_expires:
        return _apple_jwks_cache
    async with httpx.AsyncClient() as client:
        resp = await client.get(APPLE_JWKS_URL)
    resp.raise_for_status()
    _apple_jwks_cache = resp.json()["keys"]
    _apple_jwks_cache_expires = now + timedelta(hours=24)
    return _apple_jwks_cache


async def verify_apple_token(identity_token: str) -> dict:
    global _apple_jwks_cache, _apple_jwks_cache_expires
    header = jwt.get_unverified_header(identity_token)
    kid = header.get("kid")

    keys = await _get_apple_jwks()
    key_data = next((k for k in keys if k["kid"] == kid), None)

    if key_data is None:
        _apple_jwks_cache = None
        _apple_jwks_cache_expires = None
        keys = await _get_apple_jwks()
        key_data = next((k for k in keys if k["kid"] == kid), None)

    if key_data is None:
        raise ValueError(f"Unknown Apple key ID: {kid}")

    public_key = RSAAlgorithm.from_jwk(json.dumps(key_data))
    bundle_id = os.environ["APPLE_BUNDLE_ID"]

    return jwt.decode(
        identity_token,
        public_key,
        algorithms=["RS256"],
        audience=bundle_id,
        issuer="https://appleid.apple.com",
    )
```

- [ ] **Step 3: Commit**

```bash
git add src/api/auth.py
git commit -m "feat: add Apple JWKS cache and verify_apple_token helper"
```

---

## Task 2: Add AppleTokenRequest model and POST /auth/oauth/apple/token endpoint

**Files:**
- Modify: `src/api/auth.py`
- Create: `tests/api/auth/test_apple_sign_in.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/auth/test_apple_sign_in.py`:

```python
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient

from src.db.database import get_db
from src.db.tables import User
from src.main import app

FAKE_BUNDLE_ID = "com.test.whatsthatgame"

VALID_CLAIMS = {
    "iss": "https://appleid.apple.com",
    "aud": FAKE_BUNDLE_ID,
    "sub": "apple-sub-12345",
    "email": "appleuser@privaterelay.appleid.com",
    "exp": 9999999999,
}


def _mock_verify(claims: dict = None, raises: Exception = None):
    if raises:
        async def _raise(*a, **kw):
            raise raises
        return _raise
    async def _ok(*a, **kw):
        return claims or VALID_CLAIMS
    return _ok


def _client(db):
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_apple_token_new_user_returns_200(db):
    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify()):
            response = client.post("/auth/oauth/apple/token", json={
                "identity_token": "fake-token",
                "firstname": "Max",
                "lastname": "Swaine",
            })
        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/api/auth/test_apple_sign_in.py::test_apple_token_new_user_returns_200 -v
```

Expected: `FAILED` — `404 Not Found` (endpoint doesn't exist yet).

- [ ] **Step 3: Add AppleTokenRequest model and endpoint to src/api/auth.py**

Add the model after the existing `GoogleTokenRequest` class (around line 340):

```python
class AppleTokenRequest(BaseModel):
    identity_token: str
    firstname: str = ""
    lastname: str = ""
```

Add the endpoint after `google_token_exchange`:

```python
@router.post("/oauth/apple/token", tags=["oauth"], responses={
    400: {"description": "Invalid identity token, audience mismatch, or email conflict."}
})
async def apple_token_exchange(
        payload: AppleTokenRequest,
        db: Annotated[Session, Depends(get_db)],
):
    try:
        claims = await verify_apple_token(payload.identity_token)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Apple identity token")

    sub = claims.get("sub")
    email = claims.get("email")

    if not sub or not email:
        raise HTTPException(status_code=400, detail="Missing required Apple account data")

    user = db.query(User).filter(
        User.oauth_provider == "apple",
        User.oauth_id == sub,
    ).first()

    if user and not user.is_active:
        _maybe_reactivate(user, db)
        db.refresh(user)

    is_new_user = user is None

    if is_new_user:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already linked to another account")

        user = User(
            email=email,
            username=generate_unique_username(db, email.split("@")[0]),
            firstname=payload.firstname,
            lastname=payload.lastname,
            created_at=datetime.now(timezone.utc),
            oauth_provider="apple",
            oauth_id=sub,
            avatar_url=None,
            country_of_origin=None,
            date_of_birth=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    jwt_token = create_access_token(data={"sub": user.username})

    return {
        "access_token": jwt_token,
        "token_type": "bearer",
        "is_new_user": is_new_user,
    }
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
pytest tests/api/auth/test_apple_sign_in.py::test_apple_token_new_user_returns_200 -v
```

Expected: `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/api/auth.py tests/api/auth/test_apple_sign_in.py
git commit -m "feat: add POST /auth/oauth/apple/token endpoint"
```

---

## Task 3: Test new user response shape and is_new_user flag

**Files:**
- Modify: `tests/api/auth/test_apple_sign_in.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/auth/test_apple_sign_in.py`:

```python
def test_apple_token_new_user_returns_access_token(db):
    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify()):
            response = client.post("/auth/oauth/apple/token", json={
                "identity_token": "fake-token",
                "firstname": "Max",
                "lastname": "Swaine",
            })
        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
    finally:
        app.dependency_overrides.clear()


def test_apple_token_new_user_returns_is_new_user_true(db):
    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify()):
            response = client.post("/auth/oauth/apple/token", json={
                "identity_token": "fake-token",
                "firstname": "Max",
                "lastname": "Swaine",
            })
        assert response.json()["is_new_user"] is True
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/api/auth/test_apple_sign_in.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 3: Commit**

```bash
git add tests/api/auth/test_apple_sign_in.py
git commit -m "test: assert new Apple user response shape"
```

---

## Task 4: Test new user created in DB with correct fields

**Files:**
- Modify: `tests/api/auth/test_apple_sign_in.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/auth/test_apple_sign_in.py`:

```python
def test_apple_token_new_user_created_in_db(db):
    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify()):
            client.post("/auth/oauth/apple/token", json={
                "identity_token": "fake-token",
                "firstname": "Max",
                "lastname": "Swaine",
            })
        user = db.query(User).filter(User.oauth_id == "apple-sub-12345").first()
        assert user is not None
        assert user.email == "appleuser@privaterelay.appleid.com"
        assert user.oauth_provider == "apple"
        assert user.firstname == "Max"
        assert user.lastname == "Swaine"
        assert user.hashed_password is None
        assert user.avatar_url is None
    finally:
        app.dependency_overrides.clear()


def test_apple_token_new_user_without_name_uses_empty_strings(db):
    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify()):
            client.post("/auth/oauth/apple/token", json={
                "identity_token": "fake-token",
            })
        user = db.query(User).filter(User.oauth_id == "apple-sub-12345").first()
        assert user.firstname == ""
        assert user.lastname == ""
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/api/auth/test_apple_sign_in.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 3: Commit**

```bash
git add tests/api/auth/test_apple_sign_in.py
git commit -m "test: assert Apple user DB fields and name fallback"
```

---

## Task 5: Test returning user

**Files:**
- Modify: `tests/api/auth/test_apple_sign_in.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/auth/test_apple_sign_in.py`:

```python
def test_apple_token_existing_user_returns_is_new_user_false(db):
    existing = User(
        email="appleuser@privaterelay.appleid.com",
        username="appleuser",
        firstname="Max",
        lastname="Swaine",
        oauth_provider="apple",
        oauth_id="apple-sub-12345",
    )
    db.add(existing)
    db.commit()

    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify()):
            response = client.post("/auth/oauth/apple/token", json={
                "identity_token": "fake-token",
            })
        assert response.json()["is_new_user"] is False
    finally:
        app.dependency_overrides.clear()


def test_apple_token_existing_user_not_duplicated_in_db(db):
    existing = User(
        email="appleuser@privaterelay.appleid.com",
        username="appleuser",
        firstname="Max",
        lastname="Swaine",
        oauth_provider="apple",
        oauth_id="apple-sub-12345",
    )
    db.add(existing)
    db.commit()

    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify()):
            client.post("/auth/oauth/apple/token", json={"identity_token": "fake-token"})
        count = db.query(User).filter(User.oauth_id == "apple-sub-12345").count()
        assert count == 1
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/api/auth/test_apple_sign_in.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 3: Commit**

```bash
git add tests/api/auth/test_apple_sign_in.py
git commit -m "test: assert returning Apple user is not duplicated"
```

---

## Task 6: Test inactive user within 30 days is reactivated

**Files:**
- Modify: `tests/api/auth/test_apple_sign_in.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/api/auth/test_apple_sign_in.py`:

```python
def test_apple_token_inactive_user_within_30_days_is_reactivated(db):
    inactive = User(
        email="appleuser@privaterelay.appleid.com",
        username="appleuser",
        firstname="Max",
        lastname="Swaine",
        oauth_provider="apple",
        oauth_id="apple-sub-12345",
        is_active=False,
        deletion_requested_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    db.add(inactive)
    db.commit()

    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify()):
            response = client.post("/auth/oauth/apple/token", json={"identity_token": "fake-token"})
        assert response.status_code == 200
        db.refresh(inactive)
        assert inactive.is_active is True
        assert inactive.deletion_requested_at is None
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/api/auth/test_apple_sign_in.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 3: Commit**

```bash
git add tests/api/auth/test_apple_sign_in.py
git commit -m "test: assert inactive Apple user is reactivated within 30-day window"
```

---

## Task 7: Test email conflict returns 400

**Files:**
- Modify: `tests/api/auth/test_apple_sign_in.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/api/auth/test_apple_sign_in.py`:

```python
def test_apple_token_email_conflict_with_google_user_returns_400(db):
    google_user = User(
        email="appleuser@privaterelay.appleid.com",
        username="appleuser",
        firstname="Max",
        lastname="Swaine",
        oauth_provider="google",
        oauth_id="google-sub-99999",
    )
    db.add(google_user)
    db.commit()

    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify()):
            response = client.post("/auth/oauth/apple/token", json={"identity_token": "fake-token"})
        assert response.status_code == 400
        assert "already linked" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/api/auth/test_apple_sign_in.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 3: Commit**

```bash
git add tests/api/auth/test_apple_sign_in.py
git commit -m "test: assert email conflict with existing provider returns 400"
```

---

## Task 8: Test invalid token and missing claims return 400

**Files:**
- Modify: `tests/api/auth/test_apple_sign_in.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/auth/test_apple_sign_in.py`:

```python
def test_apple_token_invalid_token_returns_400(db):
    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify(raises=ValueError("bad token"))):
            response = client.post("/auth/oauth/apple/token", json={"identity_token": "bad-token"})
        assert response.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_apple_token_missing_sub_returns_400(db):
    claims_no_sub = {**VALID_CLAIMS, "sub": None}
    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify(claims=claims_no_sub)):
            response = client.post("/auth/oauth/apple/token", json={"identity_token": "fake-token"})
        assert response.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_apple_token_missing_email_returns_400(db):
    claims_no_email = {**VALID_CLAIMS, "email": None}
    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify(claims=claims_no_email)):
            response = client.post("/auth/oauth/apple/token", json={"identity_token": "fake-token"})
        assert response.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_apple_token_missing_body_returns_422(db):
    client = _client(db)
    try:
        response = client.post("/auth/oauth/apple/token", json={})
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/api/auth/test_apple_sign_in.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 3: Commit**

```bash
git add tests/api/auth/test_apple_sign_in.py
git commit -m "test: assert invalid token and missing claims return 400"
```

---

## Task 9: Run full test suite and add APPLE_BUNDLE_ID to Railway

**Files:**
- No code changes

- [ ] **Step 1: Run full test suite**

```bash
pytest -v
```

Expected: all tests `PASSED`. No regressions.

- [ ] **Step 2: Add env var to Railway**

In the Railway dashboard, add to the backend service environment:

```
APPLE_BUNDLE_ID=com.yourcompany.whatsthatgame
```

Replace `com.yourcompany.whatsthatgame` with the exact Bundle Identifier from Xcode → target → General → Identity → Bundle Identifier.

- [ ] **Step 3: Final commit (if any stray changes)**

```bash
git status
```

If clean, no commit needed. Deploy to Railway by merging to master via PR.
