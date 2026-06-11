# Account Deletion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 500 crash on `DELETE /users/{user_id}` and replace it with a GDPR-compliant two-stage soft-delete with a 30-day recovery window.

**Architecture:** Stage 1 deactivates the account on request (soft delete, no data removed). Stage 2 is an APScheduler daily sweep that purges users past the 30-day window — anonymising public games via a permanent `deleted-user` placeholder and hard-deleting everything else. A `POST /users/reactivate` endpoint lets password-based users cancel deletion within the window; OAuth users reactivate by logging in normally.

**Tech Stack:** FastAPI, SQLAlchemy 2.x (legacy query interface), APScheduler 3.x, pytest, SQLite (tests), PostgreSQL (prod).

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `src/utils/config.py` | Modify | Add `DELETED_USER_ID` constant |
| `src/db/tables.py` | Modify | Add `deletion_requested_at` column to `User` |
| `src/models/user_models/user.py` | Modify | Add `UserReactivate` Pydantic model |
| `src/api/users.py` | Modify | Soft-delete endpoint, reactivate endpoint |
| `src/api/auth.py` | Modify | OAuth reactivation check in `google_callback` |
| `src/main.py` | Modify | Add lifespan for scheduler start/stop |
| `src/core/scheduler.py` | Create | APScheduler instance |
| `src/services/purge.py` | Create | Purge logic |
| `scripts/seed_deleted_user.py` | Create | One-time seeder for placeholder account |
| `requirements.txt` | Modify | Add `apscheduler` |
| `PRIVACY_POLICY.md` | Modify | Update §8 and §9 |
| `tests/conftest.py` | Modify | Add session-scoped placeholder seed fixture |
| `tests/api/users/test_users_delete.py` | Modify | Replace old hard-delete tests with soft-delete tests |
| `tests/services/__init__.py` | Create | Package marker |
| `tests/services/test_purge.py` | Create | Purge service tests |

---

## Context for Every Task

- Python 3.14, FastAPI 0.128, SQLAlchemy 2.0.45 (legacy `db.query()` interface used throughout)
- Run tests with: `DATABASE_URL="sqlite:///./test.db" pytest` (never plain `pytest` — `.env` points to Postgres)
- Run single file: `DATABASE_URL="sqlite:///./test.db" pytest tests/path/test.py -v`
- Tests use SQLite with transaction-rollback isolation. Each test function gets a fresh `db` fixture that rolls back after the test.
- `test_user` fixture: `username="testuser"`, `email="test@example.com"`, `hashed_password` = bcrypt hash of `"password"`
- `DELETED_USER_ID = "00000000-0000-0000-0000-000000000001"` — fixed UUID for the placeholder account
- SQLite stores `DateTime` as naive datetimes even when inserted with timezone-aware values. Always normalise: `if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)`

---

## Task 1: DB Column + Config Constant

**Files:**
- Modify: `src/utils/config.py`
- Modify: `src/db/tables.py`

No test for this task — the column is exercised by Tasks 2–6.

- [ ] **Step 1: Add DELETED_USER_ID to config**

Edit `src/utils/config.py` to add the constant at the bottom:

```python
import os

from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
DUPLICATE_SIMILARITY_THRESHOLD: float = float(
    os.getenv("DUPLICATE_SIMILARITY_THRESHOLD", "0.88")
)
DELETED_USER_ID: str = "00000000-0000-0000-0000-000000000001"
```

- [ ] **Step 2: Add deletion_requested_at column to User**

In `src/db/tables.py`, find the `User` class. Add `deletion_requested_at` after `last_updated` (around line 27):

```python
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    deletion_requested_at = Column(DateTime, nullable=True)
```

- [ ] **Step 3: Verify schema compiles**

Run:
```bash
DATABASE_URL="sqlite:///./test.db" python -c "from src.db.tables import User; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/utils/config.py src/db/tables.py
git commit -m "feat: add deletion_requested_at column and DELETED_USER_ID constant"
```

---

## Task 2: Seeder Script

**Files:**
- Create: `scripts/seed_deleted_user.py`

- [ ] **Step 1: Create the seeder**

Create `scripts/seed_deleted_user.py`:

```python
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone

from src.db.database import SessionLocal
from src.db.tables import User
from src.utils.config import DELETED_USER_ID


def seed_deleted_user() -> None:
    db = SessionLocal()
    try:
        if db.query(User).filter(User.id == DELETED_USER_ID).first():
            print("deleted-user already exists, skipping")
            return
        placeholder = User(
            id=DELETED_USER_ID,
            firstname="Deleted",
            lastname="User",
            username="deleted-user",
            email="deleted@internal",
            hashed_password=None,
            is_active=False,
            created_at=datetime.now(timezone.utc),
            last_updated=datetime.now(timezone.utc),
        )
        db.add(placeholder)
        db.commit()
        print("deleted-user seeded successfully")
    finally:
        db.close()


if __name__ == "__main__":
    seed_deleted_user()
```

- [ ] **Step 2: Verify idempotency manually**

```bash
DATABASE_URL="sqlite:///./test.db" python scripts/seed_deleted_user.py
DATABASE_URL="sqlite:///./test.db" python scripts/seed_deleted_user.py
```

Expected first run: `deleted-user seeded successfully`
Expected second run: `deleted-user already exists, skipping`

- [ ] **Step 3: Commit**

```bash
git add scripts/seed_deleted_user.py
git commit -m "feat: add seed_deleted_user.py seeder script"
```

---

## Task 3: Fix DELETE Endpoint (Soft Delete)

**Files:**
- Modify: `src/api/users.py`
- Modify: `tests/api/users/test_users_delete.py`

The current `DELETE /users/{user_id}` calls `db.delete(user)` which raises `IntegrityError` for users with games. Replace the entire endpoint with a soft-delete at `DELETE /users/me`.

- [ ] **Step 1: Write failing tests**

Replace the entire content of `tests/api/users/test_users_delete.py`:

```python
import uuid
from datetime import datetime, timezone

import pytest

from src.db.tables import User, Game


def test_delete_account_deactivates_user(client_with_auth, test_user, db):
    response = client_with_auth.delete("/users/me")
    assert response.status_code == 200
    assert "30 days" in response.json()["message"]
    db.refresh(test_user)
    assert test_user.is_active is False
    assert test_user.deletion_requested_at is not None


def test_delete_account_with_game_returns_200_not_500(client_with_auth, test_user, db):
    game = Game(
        id=str(uuid.uuid4()),
        name="Test Game",
        description="A game",
        age_rating="7+",
        game_type="card",
        min_players=2,
        max_players=4,
        duration="30-45 min",
        objective="Win",
        setup="Setup steps",
        rules="The rules",
        contributor_id=test_user.id,
        is_public=True,
    )
    db.add(game)
    db.commit()

    response = client_with_auth.delete("/users/me")
    assert response.status_code == 200


def test_delete_account_unauthenticated_returns_401(client_no_auth):
    response = client_no_auth.delete("/users/me")
    assert response.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
DATABASE_URL="sqlite:///./test.db" pytest tests/api/users/test_users_delete.py -v
```

Expected: FAIL (old endpoint is `/users/{user_id}`, not `/users/me`)

- [ ] **Step 3: Replace the DELETE endpoint in users.py**

In `src/api/users.py`, find the `delete_account` function (around line 209). Replace it entirely:

```python
# DELETE
@router.delete("/me", status_code=200)
def delete_account(
        current_user: Annotated[User, Depends(get_current_active_user)],
        db: Annotated[Session, Depends(get_db)]
):
    current_user.is_active = False
    current_user.deletion_requested_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "message": "Account deactivated. You have 30 days to reactivate before your data is permanently deleted."
    }
```

Also add `deletion_requested_at` to the import at the top — the `datetime` import is already present (`from datetime import datetime, timezone`). No new import needed.

- [ ] **Step 4: Run tests to verify they pass**

```bash
DATABASE_URL="sqlite:///./test.db" pytest tests/api/users/test_users_delete.py -v
```

Expected: 3 PASS

- [ ] **Step 5: Run full suite to check for regressions**

```bash
DATABASE_URL="sqlite:///./test.db" pytest -v
```

Expected: all passing (the old `test_delete_account_forbidden_for_different_user` is gone — replaced by the new tests).

- [ ] **Step 6: Commit**

```bash
git add src/api/users.py tests/api/users/test_users_delete.py
git commit -m "fix: replace hard-delete with soft-delete on DELETE /users/me"
```

---

## Task 4: POST /users/reactivate

**Files:**
- Modify: `src/models/user_models/user.py`
- Modify: `src/api/users.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/users/test_users_reactivate.py`:

```python
import uuid
from datetime import datetime, timezone, timedelta

from src.db.tables import User


HASHED_PASSWORD = "$2b$12$b/B6ENyF.s93r2xvNx5ksuVdh.819Wvs5Q/GaHQlpO/F11.TC.SXe"  # "password"


def _make_inactive_user(db, *, days_ago: int, username: str = None, email: str = None):
    suffix = str(uuid.uuid4())[:8]
    user = User(
        id=str(uuid.uuid4()),
        firstname="React",
        lastname="Test",
        username=username or f"reactuser_{suffix}",
        email=email or f"react_{suffix}@example.com",
        hashed_password=HASHED_PASSWORD,
        is_active=False,
        deletion_requested_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        created_at=datetime.now(timezone.utc),
        last_updated=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_reactivate_within_window_returns_200_and_token(client_no_auth, db):
    user = _make_inactive_user(db, days_ago=5, email="react_valid@example.com")

    response = client_no_auth.post(
        "/users/reactivate",
        json={"email": "react_valid@example.com", "password": "password"},
    )

    assert response.status_code == 200
    assert "access_token" in response.json()
    db.refresh(user)
    assert user.is_active is True
    assert user.deletion_requested_at is None


def test_reactivate_after_30_days_returns_400(client_no_auth, db):
    _make_inactive_user(db, days_ago=31, email="react_expired@example.com")

    response = client_no_auth.post(
        "/users/reactivate",
        json={"email": "react_expired@example.com", "password": "password"},
    )

    assert response.status_code == 400


def test_reactivate_wrong_password_returns_400(client_no_auth, db):
    _make_inactive_user(db, days_ago=5, email="react_badpw@example.com")

    response = client_no_auth.post(
        "/users/reactivate",
        json={"email": "react_badpw@example.com", "password": "wrongpassword"},
    )

    assert response.status_code == 400


def test_reactivate_unknown_email_returns_400(client_no_auth):
    response = client_no_auth.post(
        "/users/reactivate",
        json={"email": "nobody@example.com", "password": "password"},
    )

    assert response.status_code == 400


def test_reactivate_active_user_returns_400(client_no_auth, test_user):
    response = client_no_auth.post(
        "/users/reactivate",
        json={"email": "test@example.com", "password": "password"},
    )

    assert response.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
DATABASE_URL="sqlite:///./test.db" pytest tests/api/users/test_users_reactivate.py -v
```

Expected: FAIL (endpoint doesn't exist)

- [ ] **Step 3: Add UserReactivate model**

In `src/models/user_models/user.py`, add at the bottom:

```python
class UserReactivate(BaseModel):
    email: str
    password: str
```

- [ ] **Step 4: Add reactivate endpoint to users.py**

Add these imports to `src/api/users.py` (if not already present):

```python
import os
from datetime import datetime, timezone, timedelta
from fastapi.responses import JSONResponse
from src.core.security import create_access_token, verify_password, TOKEN_EXPIRES_MINUTES
from src.models.user_models.user import UserReactivate
```

Then add the endpoint after `update_my_password` and before the `delete_account` function:

```python
IS_PRODUCTION = os.getenv("ENV") == "production"


@router.post("/reactivate", status_code=200)
def reactivate_account(
        body: UserReactivate,
        db: Annotated[Session, Depends(get_db)],
):
    user = db.query(User).filter(func.lower(User.email) == body.email.lower()).first()

    if not user or not user.hashed_password or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    if user.is_active or user.deletion_requested_at is None:
        raise HTTPException(status_code=400, detail="Account is not scheduled for deletion")

    deletion_time = user.deletion_requested_at
    if deletion_time.tzinfo is None:
        deletion_time = deletion_time.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) - deletion_time > timedelta(days=30):
        raise HTTPException(status_code=400, detail="Reactivation window has expired")

    user.is_active = True
    user.deletion_requested_at = None
    db.commit()

    access_token = create_access_token(data={"sub": user.username})
    response = JSONResponse(content={"access_token": access_token, "token_type": "bearer"})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="none" if IS_PRODUCTION else "lax",
        max_age=TOKEN_EXPIRES_MINUTES * 60,
    )
    return response
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
DATABASE_URL="sqlite:///./test.db" pytest tests/api/users/test_users_reactivate.py -v
```

Expected: 5 PASS

- [ ] **Step 6: Run full suite**

```bash
DATABASE_URL="sqlite:///./test.db" pytest -v
```

Expected: all passing.

- [ ] **Step 7: Commit**

```bash
git add src/models/user_models/user.py src/api/users.py tests/api/users/test_users_reactivate.py
git commit -m "feat: add POST /users/reactivate for 30-day account recovery"
```

---

## Task 5: OAuth Reactivation

**Files:**
- Modify: `src/api/auth.py`

When an OAuth user who initiated deletion logs back in via Google within the 30-day window, their account is reactivated automatically.

- [ ] **Step 1: Write a test for the reactivation helper**

Add to `tests/api/users/test_users_reactivate.py`:

```python
from datetime import timedelta
from src.api.auth import _maybe_reactivate_oauth_user


def test_maybe_reactivate_within_window(db):
    user = _make_inactive_user(db, days_ago=5, email="oauth_react@example.com")

    result = _maybe_reactivate_oauth_user(user, db)

    assert result is True
    db.refresh(user)
    assert user.is_active is True
    assert user.deletion_requested_at is None


def test_maybe_reactivate_past_window(db):
    user = _make_inactive_user(db, days_ago=31, email="oauth_expired@example.com")

    result = _maybe_reactivate_oauth_user(user, db)

    assert result is False
    db.refresh(user)
    assert user.is_active is False


def test_maybe_reactivate_active_user(db, test_user):
    result = _maybe_reactivate_oauth_user(test_user, db)

    assert result is False
```

- [ ] **Step 2: Run to verify they fail**

```bash
DATABASE_URL="sqlite:///./test.db" pytest tests/api/users/test_users_reactivate.py::test_maybe_reactivate_within_window -v
```

Expected: FAIL (`_maybe_reactivate_oauth_user` not defined)

- [ ] **Step 3: Add helper and call it in google_callback**

In `src/api/auth.py`, add the helper function after the `generate_unique_username` function (around line 32):

```python
def _maybe_reactivate_oauth_user(user: User, db: Session) -> bool:
    if user.is_active or user.deletion_requested_at is None:
        return False
    deletion_time = user.deletion_requested_at
    if deletion_time.tzinfo is None:
        deletion_time = deletion_time.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - deletion_time <= timedelta(days=30):
        user.is_active = True
        user.deletion_requested_at = None
        db.commit()
        return True
    return False
```

Add `timedelta` to the import at the top of `auth.py` (it already imports `datetime, timezone, timedelta` — verify it includes `timedelta`). If not:

```python
from datetime import datetime, timezone, timedelta
```

In `google_callback`, find the block after the user lookup (around line 231):

```python
    user = (
        db.query(User)
        .filter(
            User.oauth_provider == "google",
            User.oauth_id == oauth_id,
        )
        .first()
    )

    is_new_user = False
```

Add the reactivation check immediately after that block, before `is_new_user = False`:

```python
    if user and not user.is_active:
        _maybe_reactivate_oauth_user(user, db)
        db.refresh(user)

    is_new_user = False
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
DATABASE_URL="sqlite:///./test.db" pytest tests/api/users/test_users_reactivate.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/auth.py tests/api/users/test_users_reactivate.py
git commit -m "feat: reactivate account on OAuth login within 30-day deletion window"
```

---

## Task 6: Purge Service

**Files:**
- Create: `src/services/purge.py`
- Modify: `tests/conftest.py`
- Create: `tests/services/__init__.py`
- Create: `tests/services/test_purge.py`

The purge service finds users whose `deletion_requested_at` is past the 30-day cutoff and erases their data. The `deleted-user` placeholder (`DELETED_USER_ID`) must exist in the DB before purge runs — the conftest will seed it for tests.

- [ ] **Step 1: Add placeholder seed fixture to conftest**

In `tests/conftest.py`, add this fixture after `create_test_database`. It uses a separate session (not transaction-wrapped) so the placeholder persists for all tests:

```python
@pytest.fixture(scope="session", autouse=True)
def seed_deleted_user_placeholder(create_test_database):
    from src.utils.config import DELETED_USER_ID
    session = TestingSessionLocal()
    try:
        if not session.query(User).filter(User.id == DELETED_USER_ID).first():
            placeholder = User(
                id=DELETED_USER_ID,
                firstname="Deleted",
                lastname="User",
                username="deleted-user",
                email="deleted@internal",
                hashed_password=None,
                is_active=False,
                created_at=datetime.now(timezone.utc),
                last_updated=datetime.now(timezone.utc),
            )
            session.add(placeholder)
            session.commit()
    finally:
        session.close()
```

- [ ] **Step 2: Write failing tests**

Create `tests/services/__init__.py` (empty file).

Create `tests/services/test_purge.py`:

```python
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from src.db.tables import User, Game, GameComment, GameAlias, UserFavourites, UserAchievement
from src.services.purge import run_purge
from src.utils.config import DELETED_USER_ID


def _make_user_past_window(db) -> User:
    user = User(
        id=str(uuid.uuid4()),
        firstname="Purge",
        lastname="Me",
        username=f"purge_{uuid.uuid4().hex[:8]}",
        email=f"purge_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=None,
        is_active=False,
        deletion_requested_at=datetime.now(timezone.utc) - timedelta(days=31),
        created_at=datetime.now(timezone.utc),
        last_updated=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_purge_removes_user_past_window(db):
    user = _make_user_past_window(db)
    user_id = user.id

    run_purge(db)

    assert db.query(User).filter(User.id == user_id).first() is None


def test_purge_reassigns_public_game_to_placeholder(db):
    user = _make_user_past_window(db)
    game = Game(
        id=str(uuid.uuid4()),
        name="Public Game",
        description="desc",
        age_rating="7+",
        game_type="card",
        min_players=2,
        max_players=4,
        duration="30-45 min",
        objective="win",
        setup="setup",
        rules="rules",
        contributor_id=user.id,
        is_public=True,
    )
    db.add(game)
    db.commit()

    run_purge(db)

    db.expire(game)
    game = db.query(Game).filter(Game.id == game.id).first()
    assert game is not None
    assert game.contributor_id == DELETED_USER_ID


def test_purge_deletes_private_game(db):
    user = _make_user_past_window(db)
    game = Game(
        id=str(uuid.uuid4()),
        name="Private Game",
        description="desc",
        age_rating="7+",
        game_type="card",
        min_players=2,
        max_players=4,
        duration="30-45 min",
        objective="win",
        setup="setup",
        rules="rules",
        contributor_id=user.id,
        is_public=False,
    )
    db.add(game)
    db.commit()
    game_id = game.id

    run_purge(db)

    assert db.query(Game).filter(Game.id == game_id).first() is None


def test_purge_anonymises_comments(db):
    user = _make_user_past_window(db)
    placeholder_user = db.query(User).filter(User.id == DELETED_USER_ID).first()
    public_game = Game(
        id=str(uuid.uuid4()),
        name="Commented Game",
        description="desc",
        age_rating="7+",
        game_type="card",
        min_players=2,
        max_players=4,
        duration="30-45 min",
        objective="win",
        setup="setup",
        rules="rules",
        contributor_id=placeholder_user.id,
        is_public=True,
    )
    db.add(public_game)
    comment = GameComment(
        id=str(uuid.uuid4()),
        game_id=public_game.id,
        user_id=user.id,
        body="Great game!",
        comment_type="general",
    )
    db.add(comment)
    db.commit()
    comment_id = comment.id

    run_purge(db)

    db.expire_all()
    comment = db.query(GameComment).filter(GameComment.id == comment_id).first()
    assert comment is not None
    assert comment.user_id == DELETED_USER_ID


def test_purge_skips_user_inside_window(db):
    user = User(
        id=str(uuid.uuid4()),
        firstname="Keep",
        lastname="Me",
        username=f"keep_{uuid.uuid4().hex[:8]}",
        email=f"keep_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=None,
        is_active=False,
        deletion_requested_at=datetime.now(timezone.utc) - timedelta(days=5),
        created_at=datetime.now(timezone.utc),
        last_updated=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    user_id = user.id

    run_purge(db)

    assert db.query(User).filter(User.id == user_id).first() is not None
```

- [ ] **Step 3: Run to verify they fail**

```bash
DATABASE_URL="sqlite:///./test.db" pytest tests/services/test_purge.py -v
```

Expected: FAIL (`purge` module doesn't exist)

- [ ] **Step 4: Create src/services/purge.py**

Create `src/services/purge.py`:

```python
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from src.db.tables import (
    User, Game, UserFavourites, UserAchievement,
    GameReport, GameAlias, GameComment, CommentLike,
)
from src.utils.config import DELETED_USER_ID

PURGE_AFTER_DAYS = 30


def run_purge(db: Session) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=PURGE_AFTER_DAYS)

    candidates = db.query(User).filter(
        User.is_active == False,
        User.deletion_requested_at.isnot(None),
    ).all()

    purged = 0
    for user in candidates:
        deletion_time = user.deletion_requested_at
        if deletion_time.tzinfo is None:
            deletion_time = deletion_time.replace(tzinfo=timezone.utc)
        if deletion_time > cutoff:
            continue
        _purge_user(db, user)
        purged += 1

    return purged


def _purge_user(db: Session, user: User) -> None:
    user_id = str(user.id)

    # Collect private game IDs before deletion
    private_game_ids = [
        g.id for g in db.query(Game).filter(
            Game.contributor_id == user_id,
            Game.is_public == False,
        ).all()
    ]

    # Explicitly delete private game dependencies (SQLite FK cascade not guaranteed)
    if private_game_ids:
        comment_ids = [
            c.id for c in db.query(GameComment).filter(
                GameComment.game_id.in_(private_game_ids)
            ).all()
        ]
        if comment_ids:
            db.query(CommentLike).filter(
                CommentLike.comment_id.in_(comment_ids)
            ).delete(synchronize_session=False)
        db.query(GameComment).filter(
            GameComment.game_id.in_(private_game_ids)
        ).delete(synchronize_session=False)
        db.query(GameAlias).filter(
            GameAlias.game_id.in_(private_game_ids)
        ).delete(synchronize_session=False)
        db.query(UserFavourites).filter(
            UserFavourites.game_id.in_(private_game_ids)
        ).delete(synchronize_session=False)
        db.query(Game).filter(
            Game.id.in_(private_game_ids)
        ).delete(synchronize_session=False)

    # Reassign public games to placeholder
    db.query(Game).filter(
        Game.contributor_id == user_id,
        Game.is_public == True,
    ).update({"contributor_id": DELETED_USER_ID}, synchronize_session=False)

    # Delete user's favourites and achievements
    db.query(UserFavourites).filter(
        UserFavourites.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(UserAchievement).filter(
        UserAchievement.user_id == user_id
    ).delete(synchronize_session=False)

    # Delete user's reports
    db.query(GameReport).filter(
        GameReport.reporter_id == user_id
    ).delete(synchronize_session=False)

    # Anonymise user's comments on public games
    db.query(GameComment).filter(
        GameComment.user_id == user_id
    ).update({"user_id": DELETED_USER_ID}, synchronize_session=False)

    # Anonymise approved aliases, delete unapproved
    db.query(GameAlias).filter(
        GameAlias.suggested_by == user_id,
        GameAlias.status == "approved",
    ).update({"suggested_by": DELETED_USER_ID}, synchronize_session=False)
    db.query(GameAlias).filter(
        GameAlias.suggested_by == user_id,
        GameAlias.status != "approved",
    ).delete(synchronize_session=False)

    # Delete the user row
    db.delete(user)
    db.commit()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
DATABASE_URL="sqlite:///./test.db" pytest tests/services/test_purge.py -v
```

Expected: 5 PASS

- [ ] **Step 6: Run full suite**

```bash
DATABASE_URL="sqlite:///./test.db" pytest -v
```

Expected: all passing.

- [ ] **Step 7: Commit**

```bash
git add src/services/purge.py tests/conftest.py tests/services/__init__.py tests/services/test_purge.py
git commit -m "feat: add purge service for 30-day account deletion sweep"
```

---

## Task 7: APScheduler + Lifespan

**Files:**
- Create: `src/core/scheduler.py`
- Modify: `src/main.py`
- Modify: `requirements.txt`

The scheduler runs the purge daily at midnight. It only starts when the DB is not SQLite (i.e., production) to avoid background threads during tests.

- [ ] **Step 1: Add apscheduler to requirements.txt**

In `requirements.txt`, add at the bottom:

```
apscheduler==3.11.0
```

- [ ] **Step 2: Install it**

```bash
pip install apscheduler==3.11.0
```

Expected: successful install.

- [ ] **Step 3: Create src/core/scheduler.py**

```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
```

- [ ] **Step 4: Add lifespan to main.py**

In `src/main.py`, add these imports at the top of the file (after existing imports):

```python
from contextlib import asynccontextmanager
from src.core.scheduler import scheduler
from src.services.purge import run_purge
from src.db.database import SessionLocal
```

Add the lifespan function and helper before `app = FastAPI(...)`:

```python
def _run_purge_job() -> None:
    db = SessionLocal()
    try:
        run_purge(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if "sqlite" not in str(engine.url):
        scheduler.add_job(_run_purge_job, "cron", hour=0, minute=0, id="daily_purge")
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)
```

Change `app = FastAPI(version=APP_VERSION)` to:

```python
app = FastAPI(lifespan=lifespan, version=APP_VERSION)
```

Keep `Base.metadata.create_all(bind=engine)` at module level unchanged.

- [ ] **Step 5: Verify app starts**

```bash
DATABASE_URL="sqlite:///./test.db" python -c "from src.main import app; print('OK')"
```

Expected: `OK` (no import errors)

- [ ] **Step 6: Run full test suite**

```bash
DATABASE_URL="sqlite:///./test.db" pytest -v
```

Expected: all passing. Scheduler does not start in test mode (SQLite URL detected).

- [ ] **Step 7: Commit**

```bash
git add src/core/scheduler.py src/main.py requirements.txt
git commit -m "feat: add APScheduler with daily purge job at midnight"
```

---

## Task 8: Privacy Policy Update

**Files:**
- Modify: `PRIVACY_POLICY.md`

Update §8 (data retention) and §9 (user rights) to reflect the two-stage soft-delete. Also update "Last updated" date.

- [ ] **Step 1: Update §8 in PRIVACY_POLICY.md**

Replace the current §8 content:

```markdown
## 8. How long we keep data

- Account and content data: kept while your account is active.
- When you delete your account, your user record and associated content are deleted from our database (see §9).
- Analytics data is retained according to Amplitude's retention settings.
- Backups and logs are kept for a limited period for security and recovery, then deleted.
```

With:

```markdown
## 8. How long we keep data

- **Active accounts:** account data and content are kept while your account is active.
- **Account deletion — Stage 1 (Day 0):** when you request deletion, your account is deactivated immediately and login is blocked. Your data is not yet deleted.
- **Recovery window (Days 1–30):** you can reactivate your account and restore full access within 30 days of requesting deletion.
- **Account deletion — Stage 2 (Day 30):** after the 30-day window expires, we permanently erase your personal data (name, email, date of birth, country, avatar, authentication credentials). Private games and their associated content are deleted. Public games you contributed are retained anonymously (attributed to "Deleted user") so the platform catalogue remains useful. Comments you posted are retained anonymously. User reports, favourites, and achievements are deleted.
- **Analytics data** is retained according to Amplitude's retention settings.
- **Backups and logs** are kept for a limited period for security and recovery, then deleted.
```

- [ ] **Step 2: Update §9 in PRIVACY_POLICY.md**

Replace the current §9 delete bullet:

```markdown
- **Delete your account:** you can delete your account from within the app. This removes your user record from our database. You can also email us at **whatsthatgameteam@gmail.com**.
```

With:

```markdown
- **Delete your account:** you can request deletion from within the app. Your account is deactivated immediately and permanently erased after 30 days (see §8). You can cancel deletion and reactivate within those 30 days. You can also email us at **whatsthatgameteam@gmail.com** for manual erasure requests.
```

- [ ] **Step 3: Update the "Last updated" date**

Change the date at the top of `PRIVACY_POLICY.md`:

```markdown
**Last updated:** 11 June 2026
```

- [ ] **Step 4: Commit**

```bash
git add PRIVACY_POLICY.md
git commit -m "docs: update privacy policy §8 and §9 for two-stage soft-delete"
```

---

## Deployment Checklist (Railway — do before merging to master)

1. **Run manual SQL on production DB** (required — no Alembic):
   ```sql
   ALTER TABLE users ADD COLUMN deletion_requested_at TIMESTAMP;
   ```

2. **Run seeder once on production:**
   ```bash
   python scripts/seed_deleted_user.py
   ```
   Verify output: `deleted-user seeded successfully` or `already exists`.

3. **Deploy** — `create_all` auto-creates any new tables (none added in this feature). The lifespan starts the APScheduler on app boot.

4. **Update `index.html` in `maxswaine/WhatsThatGamePrivacyPolicy` repo** — apply the same §8 and §9 changes to match `PRIVACY_POLICY.md`.

---

## Frontend Changes

| Endpoint | Change | Frontend action |
|---|---|---|
| `DELETE /users/{user_id}` | Replaced by `DELETE /users/me` | Update delete URL, remove `user_id` from path |
| `DELETE /users/me` response | 200 with message (not 204) | Show "30-day recovery" confirmation rather than immediate "account deleted" |
| `POST /users/reactivate` | New | Add reactivation screen accessible from login page |
| OAuth login | Transparent reactivation | No change — existing OAuth flow handles it |
