# OAuth Duplicate Email Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent a user from ending up with two accounts sharing the same email across auth methods (password, Google, Apple), and add a DB-level unique constraint on `email` as a backstop.

**Architecture:** Three OAuth/password signup paths currently have inconsistent duplicate-email handling. `/register` already blocks (case-insensitive). Apple's `/auth/oauth/apple/token` blocks but case-sensitively. Google's `/auth/oauth/google/callback` and `/auth/oauth/google/token` don't block at all. This plan makes all three case-insensitive and consistent, then backstops with a DB unique constraint.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, TestClient.

## Global Constraints

- Reject-on-conflict only — no account linking (spec explicitly rejects this).
- Case-insensitive email comparison everywhere (`func.lower(...)` on both sides), consistent with `/register`'s existing check.
- No Alembic — this repo uses `Base.metadata.create_all` on startup, which never alters existing tables. The `unique=True` column change only affects fresh databases (tests, new environments). The existing Railway Postgres `users` table needs a manual, one-time `ALTER TABLE` — this plan does NOT execute that against Railway; it's called out as a manual step for the user at the end.
- Error response for all three conflict cases: `HTTPException(status_code=400, detail="Email already linked to another account")` — exact string, matches Apple's existing message.

---

### Task 1: Case-insensitive email check for Apple OAuth

**Files:**
- Modify: `src/api/auth.py:577-579`
- Test: `tests/api/auth/test_apple_sign_in.py`

**Interfaces:**
- Consumes: `func` from `sqlalchemy` (already imported in `src/api/auth.py:14`), `User` model (`src/db/tables.py`).
- Produces: no new interface — this task only tightens an existing check's comparison.

Current code at `src/api/auth.py:577-579`:
```python
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already linked to another account")
```

- [ ] **Step 1: Write the failing test**

Add to `tests/api/auth/test_apple_sign_in.py` (append after `test_apple_token_email_conflict_with_google_user_returns_400`, around line 229):

```python
def test_apple_token_email_conflict_case_insensitive_returns_400(db):
    google_user = User(
        email="AppleUser@PrivateRelay.AppleID.com",
        username="appleuser2",
        firstname="Max",
        lastname="Swaine",
        oauth_provider="google",
        oauth_id="google-sub-88888",
    )
    db.add(google_user)
    db.commit()

    client = _client(db)
    try:
        with patch("src.api.auth.verify_apple_token", _mock_verify()):
            response = client.post("/auth/oauth/apple/token", json={"identity_token": "fake-token"})
        assert response.status_code == 400
        assert response.json()["detail"] == "Email already linked to another account"
    finally:
        app.dependency_overrides.clear()
```

Note: `VALID_CLAIMS["email"]` is `"appleuser@privaterelay.appleid.com"` (lowercase) — the existing user row uses mixed case, so this only passes once the comparison is case-insensitive.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/auth/test_apple_sign_in.py::test_apple_token_email_conflict_case_insensitive_returns_400 -v`
Expected: FAIL — response status is 200, not 400 (new user created because case-sensitive query didn't match).

- [ ] **Step 3: Write minimal implementation**

Replace `src/api/auth.py:577-579` with:

```python
        existing = db.query(User).filter(func.lower(User.email) == func.lower(email)).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already linked to another account")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/auth/test_apple_sign_in.py -v`
Expected: all tests in the file PASS, including the new one and the pre-existing `test_apple_token_email_conflict_with_google_user_returns_400`.

- [ ] **Step 5: Commit**

```bash
git add src/api/auth.py tests/api/auth/test_apple_sign_in.py
git commit -m "fix(auth): make apple oauth email-conflict check case-insensitive"
```

---

### Task 2: Email-conflict guard for native Google OAuth (`/auth/oauth/google/token`)

**Files:**
- Modify: `src/api/auth.py:507-524`
- Test: `tests/api/auth/test_google_oauth_native.py`

**Interfaces:**
- Consumes: `func`, `User`, same pattern as Task 1.
- Produces: no new interface.

Current code at `src/api/auth.py:507-524`:
```python
    is_new_user = user is None

    if is_new_user:
        user = User(
            email=email,
            username=generate_unique_username(db, email.split("@")[0]),
            firstname=claims.get("given_name") or "",
            lastname=claims.get("family_name") or "",
            created_at=datetime.now(timezone.utc),
            oauth_provider="google",
            oauth_id=oauth_id,
            avatar_url=claims.get("picture"),
            country_of_origin=None,
            date_of_birth=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
```

- [ ] **Step 1: Write the failing test**

Add to `tests/api/auth/test_google_oauth_native.py` (append after `test_google_token_existing_user_not_duplicated_in_db`, around line 148):

```python
# ---------------------------------------------------------------------------
# Duplicate email
# ---------------------------------------------------------------------------

def test_google_token_duplicate_email_returns_400(db):
    existing = User(
        email="testuser@gmail.com",
        username="testuser",
        firstname="Test",
        lastname="User",
        hashed_password="hashed",
    )
    db.add(existing)
    db.commit()

    client = _client(db)
    try:
        with patch("src.api.auth.httpx.AsyncClient", _async_client_mock(VALID_TOKENINFO)), \
             patch.dict(os.environ, {"GOOGLE_CLIENT_ID": FAKE_CLIENT_ID}):
            response = client.post("/auth/oauth/google/token", json={"id_token": "fake-id-token"})
        assert response.status_code == 400
        assert response.json()["detail"] == "Email already linked to another account"
    finally:
        app.dependency_overrides.clear()


def test_google_token_duplicate_email_does_not_create_user(db):
    existing = User(
        email="testuser@gmail.com",
        username="testuser",
        firstname="Test",
        lastname="User",
        hashed_password="hashed",
    )
    db.add(existing)
    db.commit()

    client = _client(db)
    try:
        with patch("src.api.auth.httpx.AsyncClient", _async_client_mock(VALID_TOKENINFO)), \
             patch.dict(os.environ, {"GOOGLE_CLIENT_ID": FAKE_CLIENT_ID}):
            client.post("/auth/oauth/google/token", json={"id_token": "fake-id-token"})
        count = db.query(User).filter(User.email == "testuser@gmail.com").count()
        assert count == 1
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/auth/test_google_oauth_native.py::test_google_token_duplicate_email_returns_400 -v`
Expected: FAIL — response status is 200 (new Google-linked user created for an email that already belongs to a password account).

- [ ] **Step 3: Write minimal implementation**

Replace `src/api/auth.py:507-524` with:

```python
    is_new_user = user is None

    if is_new_user:
        existing = db.query(User).filter(func.lower(User.email) == func.lower(email)).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already linked to another account")

        user = User(
            email=email,
            username=generate_unique_username(db, email.split("@")[0]),
            firstname=claims.get("given_name") or "",
            lastname=claims.get("family_name") or "",
            created_at=datetime.now(timezone.utc),
            oauth_provider="google",
            oauth_id=oauth_id,
            avatar_url=claims.get("picture"),
            country_of_origin=None,
            date_of_birth=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/auth/test_google_oauth_native.py -v`
Expected: all tests in the file PASS.

- [ ] **Step 5: Commit**

```bash
git add src/api/auth.py tests/api/auth/test_google_oauth_native.py
git commit -m "fix(auth): reject google oauth signup when email already registered"
```

---

### Task 3: Email-conflict guard for browser Google OAuth (`/auth/oauth/google/callback`)

**Files:**
- Modify: `src/api/auth.py:341-359`
- Test: `tests/api/auth/test_oauth_csrf.py`

**Interfaces:**
- Consumes: `func`, `User`, same as Task 1/2.
- Produces: no new interface.

Current code at `src/api/auth.py:341-359`:
```python
    is_new_user = False

    if not user:
        is_new_user = True
        user = User(
            email=email,
            username=generate_unique_username(db, email.split("@")[0]),
            firstname=userinfo.get("given_name") or "",
            lastname=userinfo.get("family_name") or "",
            created_at=datetime.now(timezone.utc),
            oauth_provider="google",
            oauth_id=oauth_id,
            avatar_url=userinfo.get("picture"),
            country_of_origin=None,
            date_of_birth=None
        )
        db.add(user)
        db.commit()
        db.refresh(user)
```

- [ ] **Step 1: Write the failing test**

Add to `tests/api/auth/test_oauth_csrf.py`. First add these imports at the top of the file (after the existing imports, around line 8):

```python
from src.db.tables import User
```

Then append this test at the end of the file:

```python
def test_google_callback_duplicate_email_returns_400(oauth_client, db):
    existing = User(
        email="dupe@example.com",
        username="dupeuser",
        firstname="Dupe",
        lastname="User",
        hashed_password="hashed",
    )
    db.add(existing)
    db.commit()

    login_resp = oauth_client.get("/auth/oauth/google", follow_redirects=False)
    location = login_resp.headers["location"]
    state = parse_qs(urlparse(location).query)["state"][0]

    mock_token_resp = AsyncMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json = lambda: {"access_token": "fake-google-access-token"}

    mock_userinfo_resp = AsyncMock()
    mock_userinfo_resp.json = lambda: {
        "email": "dupe@example.com",
        "email_verified": True,
        "sub": "google-sub-99999",
        "given_name": "Dupe",
        "family_name": "User",
        "picture": None,
    }

    with patch("httpx.AsyncClient") as mock_cls:
        instance = mock_cls.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=mock_token_resp)
        instance.get = AsyncMock(return_value=mock_userinfo_resp)
        response = oauth_client.get(
            f"/auth/oauth/google/callback?code=testcode&state={state}",
            follow_redirects=False,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Email already linked to another account"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/auth/test_oauth_csrf.py::test_google_callback_duplicate_email_returns_400 -v`
Expected: FAIL — response is a redirect (302/307), not a 400 JSON response (new user silently created for the duplicate email).

- [ ] **Step 3: Write minimal implementation**

Replace `src/api/auth.py:341-359` with:

```python
    is_new_user = False

    if not user:
        existing = db.query(User).filter(func.lower(User.email) == func.lower(email)).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already linked to another account")

        is_new_user = True
        user = User(
            email=email,
            username=generate_unique_username(db, email.split("@")[0]),
            firstname=userinfo.get("given_name") or "",
            lastname=userinfo.get("family_name") or "",
            created_at=datetime.now(timezone.utc),
            oauth_provider="google",
            oauth_id=oauth_id,
            avatar_url=userinfo.get("picture"),
            country_of_origin=None,
            date_of_birth=None
        )
        db.add(user)
        db.commit()
        db.refresh(user)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/auth/test_oauth_csrf.py -v`
Expected: all tests in the file PASS.

- [ ] **Step 5: Commit**

```bash
git add src/api/auth.py tests/api/auth/test_oauth_csrf.py
git commit -m "fix(auth): reject google oauth browser callback for duplicate email"
```

---

### Task 4: DB-level unique constraint on `email`

**Files:**
- Modify: `src/db/tables.py:19`
- Test: `tests/api/users/` (new test in an existing file, see below)

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — this is a schema constraint, not a code interface.

Current code at `src/db/tables.py:19`:
```python
    email = Column(String, nullable=False)
```

- [ ] **Step 1: Write the failing test**

Add to `tests/api/users/test_users_post.py` (append at end of file):

```python
def test_duplicate_email_violates_db_constraint(db):
    from sqlalchemy.exc import IntegrityError
    from src.db.tables import User

    user1 = User(
        email="constraint-test@example.com",
        username="constrainttest1",
        firstname="A",
        lastname="B",
        hashed_password="hashed",
    )
    db.add(user1)
    db.commit()

    user2 = User(
        email="constraint-test@example.com",
        username="constrainttest2",
        firstname="C",
        lastname="D",
        hashed_password="hashed",
    )
    db.add(user2)
    try:
        db.commit()
        assert False, "expected IntegrityError for duplicate email"
    except IntegrityError:
        db.rollback()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/users/test_users_post.py::test_duplicate_email_violates_db_constraint -v`
Expected: FAIL — `db.commit()` succeeds for the second insert (no constraint yet), so the `assert False` line executes.

- [ ] **Step 3: Write minimal implementation**

Replace `src/db/tables.py:19` with:

```python
    email = Column(String, nullable=False, unique=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/users/test_users_post.py -v`
Expected: all tests in the file PASS. Also run the full suite to confirm the new constraint doesn't break existing fixtures/tests that create multiple users:

Run: `pytest -v`
Expected: all tests PASS. (`tests/conftest.py` drops and recreates the schema each session via `Base.metadata.create_all`, so the SQLite test DB picks up the new constraint automatically — no manual migration needed for tests.)

- [ ] **Step 5: Commit**

```bash
git add src/db/tables.py tests/api/users/test_users_post.py
git commit -m "feat(users): add db-level unique constraint on email"
```

- [ ] **Step 6: Manual production step (not automated by this plan)**

`Base.metadata.create_all` (used in `src/main.py` on startup) only creates missing tables — it will NOT alter the existing `users` table on Railway's Postgres to add this constraint. Before or immediately after deploying this change, run directly against the Railway Postgres instance:

```sql
ALTER TABLE users ADD CONSTRAINT users_email_key UNIQUE (email);
```

Confirm no existing rows violate it first:

```sql
SELECT email, COUNT(*) FROM users GROUP BY email HAVING COUNT(*) > 1;
```

Expected: zero rows (pre-launch, no duplicates expected). If any are found, resolve them before running the `ALTER TABLE`.

---

## Self-Review Notes

- **Spec coverage:** Google callback guard (Task 3), Google native guard (Task 2), Apple case-insensitivity (Task 1), DB constraint + manual ALTER TABLE step (Task 4) — all four spec items covered. Non-goals (account linking, data migration) correctly excluded — no task attempts either.
- **Consistency:** All three code paths use the identical `func.lower(User.email) == func.lower(email)` comparison and identical error string `"Email already linked to another account"`.
- **Order matters:** Task 4 (schema change) is independent of Tasks 1-3 and could run in any order, but is placed last since it's the only task with a manual post-deploy step — keeping it last means the deploy-and-verify step happens once at the end, not interleaved with code-only commits.
