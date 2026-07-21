# Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Push notifications for the mobile app via Expo Push Service, triggered by achievement grants and admin-sent messages (single-user or broadcast), plus a new `HALL_OF_FAME` achievement granted through a new admin game-verify endpoint.

**Architecture:** Two new tables (`push_tokens`, `notifications`). A single `src/services/notifications.py::send()` function is the only code path that calls the Expo API — everything else (the achievement-grant hook, the admin endpoint) calls through it. `send()` never raises and never commits the DB session itself; the caller controls the transaction, matching the existing best-effort external-call convention in this codebase (`games.py`'s inline embedding call).

**Tech Stack:** FastAPI, SQLAlchemy, `exponent-server-sdk` (Expo push client), pytest with `unittest.mock`.

**Reference spec:** `docs/superpowers/specs/2026-07-21-notifications-design.md`

## Global Constraints

- Tests run with `DATABASE_URL="sqlite:///./test.db"` — verify this is set before running any test command in this plan (`echo $DATABASE_URL`), export it if not: `export DATABASE_URL="sqlite:///./test.db"`.
- Multi-file/whole-suite test runs in this plan are run with `OPENAI_API_KEY=""`, not whatever real key is in `.env`. This is unrelated to notifications: a handful of pre-existing achievements/favourites tests create near-identical games ("Game 1"/"Game 2") assuming duplicate-detection is off; with a real `OPENAI_API_KEY` set, embeddings compute and dedup silently rejects the near-duplicate games, failing those tests. If a broad checkpoint in this plan fails on `TestFiveUploads`/`TestScenarios`-style tests, that's this pre-existing issue, not something this feature broke — don't "fix" it as part of this plan.
- **Never combine two client fixtures (e.g. `client_with_auth` + `client_as_admin`) in one test.** `app.dependency_overrides` is a single dict on the app object; whichever fixture sets it up last wins for the entire test body, silently collapsing both "clients" onto the same user. Use one client fixture for auth and seed any other user's data directly via the `db` fixture (see `TestTenLikes` in `tests/api/achievements/test_achievements.py` for the existing pattern).
- No Alembic. `Base.metadata.create_all(bind=engine)` in `src/main.py` auto-creates new tables on next deploy — no manual migration needed for `push_tokens`/`notifications`.
- `exponent-server-sdk==2.2.0` (confirmed available on PyPI at plan time) — pin exactly, append to `requirements.txt`.
- `notifications.send()` must never raise (all Expo/network errors caught and swallowed) and must never call `db.commit()` internally — it only `db.add()`/`db.query().delete()`s against the session it's given; the caller commits. This is required for the documented rollback-consistency behavior in the spec (§4) to actually hold.
- `HALL_OF_FAME` is added to `AchievementTypeEnum` but must NOT be added to `SIGNAL_ONLY_ACHIEVEMENTS` — it's server-granted (via the verify endpoint) and should push, unlike `share_game`/`give_feedback`/`complete_tutorial`.
- Every test in this suite must be guaranteed to never make a real network call to Expo — enforced via an autouse fixture (Task 2) that patches the real `exponent_server_sdk.PushClient.publish_multiple` to raise if invoked unmocked.
- Admin-only endpoints use the existing `require_admin` dependency (`src/api/users.py:93`) — do not write a new admin check.
- Response field naming: the DB column is `Game.is_whats_that_game_verified`; the API-facing field (via `map_game_to_read`) is `is_whats_that_game_certified`. Don't confuse the two.

---

### Task 1: Schema — `push_tokens`/`notifications` tables, `HALL_OF_FAME` achievement type

**Files:**
- Modify: `src/db/tables.py` (add `PushToken`, `Notification` classes)
- Modify: `src/models/enums/achievement_enum.py` (add `HALL_OF_FAME`)
- Modify: `tests/api/achievements/test_achievements.py:23-27` (achievement count 7 → 8)
- Test: `tests/services/test_notifications.py` (new file)

**Interfaces:**
- Produces: `src.db.tables.PushToken` (`token: str` PK, `user_id: str` FK, `platform: str`, `updated_at: datetime`)
- Produces: `src.db.tables.Notification` (`id: str` PK, `user_id: str` FK, `type: str`, `title: str`, `body: str`, `data: str | None`, `achievement_type: str | None`, `status: str`, `created_at: datetime`)
- Produces: `AchievementTypeEnum.HALL_OF_FAME = "hall_of_fame"`

- [ ] **Step 1: Write the failing schema tests**

Create `tests/services/__init__.py` if it doesn't already exist (it does — `tests/services/test_purge.py` is already there, skip this).

Create `tests/services/test_notifications.py`:

```python
import uuid

from src.db.tables import Notification, PushToken
from src.models.enums.achievement_enum import AchievementTypeEnum, SIGNAL_ONLY_ACHIEVEMENTS


class TestPushTokenSchema:
    def test_round_trip(self, db, test_user):
        db.add(PushToken(token="ExponentPushToken[abc]", user_id=test_user.id, platform="ios"))
        db.commit()

        fetched = db.query(PushToken).filter_by(token="ExponentPushToken[abc]").first()
        assert fetched is not None
        assert fetched.user_id == test_user.id
        assert fetched.platform == "ios"
        assert fetched.updated_at is not None


class TestNotificationSchema:
    def test_round_trip(self, db, test_user):
        note = Notification(
            id=str(uuid.uuid4()),
            user_id=test_user.id,
            type="custom",
            title="Hello",
            body="World",
            data=None,
            achievement_type=None,
            status="sent",
        )
        db.add(note)
        db.commit()

        fetched = db.query(Notification).filter_by(id=note.id).first()
        assert fetched is not None
        assert fetched.status == "sent"
        assert fetched.created_at is not None


class TestHallOfFameEnum:
    def test_is_a_valid_achievement_type(self):
        assert AchievementTypeEnum.HALL_OF_FAME.value == "hall_of_fame"

    def test_not_signal_only(self):
        assert AchievementTypeEnum.HALL_OF_FAME not in SIGNAL_ONLY_ACHIEVEMENTS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `DATABASE_URL="sqlite:///./test.db" pytest tests/services/test_notifications.py -v`
Expected: FAIL — `ImportError: cannot import name 'PushToken' from 'src.db.tables'` (and `AttributeError` for `HALL_OF_FAME` once that import is fixed).

- [ ] **Step 3: Add the tables and enum value**

In `src/db/tables.py`, add after the `GameComment`/`CommentLike` classes (anywhere after `Base` subclasses already defined, before `Feedback` is fine):

```python
class PushToken(Base):
    __tablename__ = "push_tokens"
    token = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = Column(String, nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    body = Column(String, nullable=False)
    data = Column(String, nullable=True)
    achievement_type = Column(String, nullable=True)
    status = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
```

In `src/models/enums/achievement_enum.py`:

```python
from enum import Enum


class AchievementTypeEnum(str, Enum):
    FIRST_LIKE = "first_like"
    FIRST_SUBMIT = "first_submit"
    SHARE_GAME = "share_game"
    FIVE_UPLOADS = "five_uploads"
    TEN_LIKES_ON_UPLOAD = "ten_likes_on_upload"
    GIVE_FEEDBACK = "give_feedback"
    COMPLETE_TUTORIAL = "complete_tutorial"
    HALL_OF_FAME = "hall_of_fame"


SIGNAL_ONLY_ACHIEVEMENTS = {
    AchievementTypeEnum.SHARE_GAME,
    AchievementTypeEnum.GIVE_FEEDBACK,
    AchievementTypeEnum.COMPLETE_TUTORIAL,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `DATABASE_URL="sqlite:///./test.db" pytest tests/services/test_notifications.py -v`
Expected: 4 passed

- [ ] **Step 5: Fix the achievement count regression this causes**

`tests/api/achievements/test_achievements.py:23-27` currently hardcodes 7 achievement types. Update:

```python
    def test_returns_all_seven_locked_for_new_user(self, client_with_auth):
        achievements = _get_achievements(client_with_auth)
        assert len(achievements) == 8
        assert all(not a["achieved"] for a in achievements)
        assert all(a["achieved_at"] is None for a in achievements)
```

(Rename the method to `test_returns_all_eight_locked_for_new_user` for accuracy.)

- [ ] **Step 6: Run the full achievements test file to confirm no other regressions**

Run: `OPENAI_API_KEY="" DATABASE_URL="sqlite:///./test.db" pytest tests/api/achievements/test_achievements.py -v`
Expected: all pass (the only other test touching the count, `test_returns_all_expected_types`, computes the expected set dynamically from the enum so it needs no change).

- [ ] **Step 7: Commit**

```bash
git add src/db/tables.py src/models/enums/achievement_enum.py tests/services/test_notifications.py tests/api/achievements/test_achievements.py
git commit -m "feat(notifications): add push_tokens/notifications tables and HALL_OF_FAME achievement type"
```

---

### Task 2: `notifications.send()` — the single Expo send path

**Files:**
- Create: `src/services/notifications.py`
- Modify: `requirements.txt` (add `exponent-server-sdk==2.2.0`)
- Modify: `tests/conftest.py` (add global network-safety autouse fixture)
- Test: `tests/services/test_notifications.py` (extend from Task 1)

**Interfaces:**
- Consumes: `src.db.tables.PushToken`, `src.db.tables.Notification` (Task 1)
- Produces: `notifications.send(db: Session, user_id: str, title: str, body: str, *, notification_type: str = "custom", data: dict | None = None, achievement_type: str | None = None) -> None` — used directly by Task 6 (admin endpoint) and indirectly by Task 3 (achievement hook, via `send_achievement_notification`).
- Produces: `notifications._get_push_client() -> PushClient` — the sole instantiation point of the Expo client, patchable in tests.

- [ ] **Step 1: Add the dependency**

```bash
source .venv/bin/activate  # or however this project's venv is activated
pip install exponent-server-sdk==2.2.0
```

Add to `requirements.txt` (append at end, matching the file's existing chronological-append style):

```
exponent-server-sdk==2.2.0
```

- [ ] **Step 2: Add the global test-safety net**

In `tests/conftest.py`, add the import and fixture (add `from unittest.mock import patch` near the top imports, and the fixture near `reset_rate_limiter`):

```python
from unittest.mock import patch
```

```python
@pytest.fixture(autouse=True)
def block_real_push_notifications():
    def _raise(*args, **kwargs):
        raise AssertionError(
            "Real Expo push call attempted in a test — mock "
            "src.services.notifications._get_push_client instead."
        )
    with patch("exponent_server_sdk.PushClient.publish_multiple", side_effect=_raise):
        yield
```

This patches the real SDK class method (not our wrapper), so it works regardless of whether `src/services/notifications.py` exists yet or how any future code calls Expo — any accidental real call anywhere in the suite fails loudly instead of silently hitting the network.

- [ ] **Step 3: Run the full test suite to confirm the safety net alone doesn't break anything**

Run: `OPENAI_API_KEY="" DATABASE_URL="sqlite:///./test.db" pytest -v`
Expected: same pass/fail state as before this step (this fixture is inert until something calls the real `PushClient.publish_multiple`, which nothing does yet).

- [ ] **Step 4: Write the failing tests for `send()`**

Append to `tests/services/test_notifications.py`:

```python
from unittest.mock import MagicMock, patch

from exponent_server_sdk import DeviceNotRegisteredError

from src.services import notifications


class TestSendNoToken:
    def test_writes_no_token_status_and_never_touches_expo(self, db, test_user):
        with patch("src.services.notifications._get_push_client") as mock_get_client:
            notifications.send(db, test_user.id, "Title", "Body")
            db.commit()

        mock_get_client.assert_not_called()
        note = db.query(Notification).filter_by(user_id=test_user.id).first()
        assert note.status == "no_token"
        assert note.title == "Title"
        assert note.body == "Body"
        assert note.type == "custom"


class TestSendSuccess:
    def test_writes_sent_status_and_calls_expo_with_data(self, db, test_user):
        db.add(PushToken(token="ExponentPushToken[abc]", user_id=test_user.id, platform="ios"))
        db.commit()

        mock_ticket = MagicMock()
        mock_ticket.validate_response.return_value = None
        mock_client = MagicMock()
        mock_client.publish_multiple.return_value = [mock_ticket]

        with patch("src.services.notifications._get_push_client", return_value=mock_client):
            notifications.send(db, test_user.id, "Title", "Body", data={"game_id": "g1"})
            db.commit()

        mock_client.publish_multiple.assert_called_once()
        note = db.query(Notification).filter_by(user_id=test_user.id).first()
        assert note.status == "sent"
        assert note.data == '{"game_id": "g1"}'


class TestSendFailure:
    def test_writes_failed_status_when_expo_call_raises(self, db, test_user):
        db.add(PushToken(token="ExponentPushToken[abc]", user_id=test_user.id, platform="ios"))
        db.commit()

        mock_client = MagicMock()
        mock_client.publish_multiple.side_effect = RuntimeError("network down")

        with patch("src.services.notifications._get_push_client", return_value=mock_client):
            notifications.send(db, test_user.id, "Title", "Body")
            db.commit()

        note = db.query(Notification).filter_by(user_id=test_user.id).first()
        assert note.status == "failed"


class TestSendPrunesDeadToken:
    def test_deletes_token_on_device_not_registered_but_still_logs_sent(self, db, test_user):
        db.add(PushToken(token="ExponentPushToken[dead]", user_id=test_user.id, platform="ios"))
        db.commit()

        mock_ticket = MagicMock()
        mock_ticket.push_message.to = "ExponentPushToken[dead]"
        mock_ticket.validate_response.side_effect = DeviceNotRegisteredError(mock_ticket)
        mock_client = MagicMock()
        mock_client.publish_multiple.return_value = [mock_ticket]

        with patch("src.services.notifications._get_push_client", return_value=mock_client):
            notifications.send(db, test_user.id, "Title", "Body")
            db.commit()

        assert db.query(PushToken).filter_by(token="ExponentPushToken[dead]").first() is None
        note = db.query(Notification).filter_by(user_id=test_user.id).first()
        assert note.status == "sent"
```

Add the missing imports at the top of `tests/services/test_notifications.py`: `from src.db.tables import Notification, PushToken` (already there from Task 1 — just confirm both are imported; no change needed if Task 1's import line already covers it).

- [ ] **Step 5: Run tests to verify they fail**

Run: `DATABASE_URL="sqlite:///./test.db" pytest tests/services/test_notifications.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.services.notifications'`

- [ ] **Step 6: Implement `send()`**

Create `src/services/notifications.py`:

```python
import json
import uuid
from typing import Optional

from exponent_server_sdk import (
    DeviceNotRegisteredError,
    PushClient,
    PushMessage,
    PushTicketError,
)
from sqlalchemy.orm import Session

from src.db.tables import Notification, PushToken

_push_client: Optional[PushClient] = None


def _get_push_client() -> PushClient:
    global _push_client
    if _push_client is None:
        _push_client = PushClient()
    return _push_client


def send(
    db: Session,
    user_id: str,
    title: str,
    body: str,
    *,
    notification_type: str = "custom",
    data: Optional[dict] = None,
    achievement_type: Optional[str] = None,
) -> None:
    tokens = db.query(PushToken).filter(PushToken.user_id == user_id).all()

    if not tokens:
        _log(db, user_id, title, body, notification_type, data, achievement_type, status="no_token")
        return

    messages = [
        PushMessage(to=t.token, title=title, body=body, data=data or {})
        for t in tokens
    ]

    try:
        tickets = _get_push_client().publish_multiple(messages)
    except Exception:
        _log(db, user_id, title, body, notification_type, data, achievement_type, status="failed")
        return

    for ticket in tickets:
        try:
            ticket.validate_response()
        except DeviceNotRegisteredError:
            db.query(PushToken).filter(PushToken.token == ticket.push_message.to).delete()
        except PushTicketError:
            pass

    _log(db, user_id, title, body, notification_type, data, achievement_type, status="sent")


def _log(db, user_id, title, body, notification_type, data, achievement_type, status) -> None:
    db.add(Notification(
        id=str(uuid.uuid4()),
        user_id=user_id,
        type=notification_type,
        title=title,
        body=body,
        data=json.dumps(data) if data else None,
        achievement_type=achievement_type,
        status=status,
    ))
```

Note: `send()` deliberately never calls `db.commit()` — every test above calls `db.commit()` itself after `send()`, exactly mirroring how real callers (Tasks 3 and 6) are required to behave.

- [ ] **Step 7: Run tests to verify they pass**

Run: `DATABASE_URL="sqlite:///./test.db" pytest tests/services/test_notifications.py -v`
Expected: 8 passed (4 from Task 1 + 4 from this task)

- [ ] **Step 8: Commit**

```bash
git add src/services/notifications.py requirements.txt tests/conftest.py tests/services/test_notifications.py
git commit -m "feat(notifications): add notifications.send() Expo push service with never-raise/never-commit guarantees"
```

---

### Task 3: Achievement hook

**Files:**
- Modify: `src/services/achievements.py`
- Modify: `src/services/notifications.py` (add `ACHIEVEMENT_COPY`, `send_achievement_notification`)
- Test: `tests/services/test_achievements.py` (new file)
- Test: `tests/services/test_notifications.py` (extend)

**Interfaces:**
- Consumes: `notifications.send()` (Task 2)
- Produces: `notifications.send_achievement_notification(db: Session, user_id: str, achievement_type: AchievementTypeEnum) -> None`
- Modifies: `achievements.grant_if_not_exists(db, user_id, achievement) -> bool` — same signature, now has a side effect of calling `send_achievement_notification` for non-signal-only types.

- [ ] **Step 1: Write the failing test for `send_achievement_notification`**

Append to `tests/services/test_notifications.py`:

```python
from src.models.enums.achievement_enum import AchievementTypeEnum


class TestSendAchievementNotification:
    def test_uses_copy_for_known_achievement_type_and_tags_data(self, db, test_user):
        with patch("src.services.notifications.send") as mock_send:
            notifications.send_achievement_notification(db, test_user.id, AchievementTypeEnum.FIRST_LIKE)

        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert args[:2] == (db, test_user.id)
        assert kwargs["notification_type"] == "achievement"
        assert kwargs["achievement_type"] == "first_like"
        assert kwargs["data"] == {"achievement_type": "first_like"}
        assert isinstance(kwargs.get("title") or args[2], str)

    def test_falls_back_to_generic_copy_for_hall_of_fame(self, db, test_user):
        with patch("src.services.notifications.send") as mock_send:
            notifications.send_achievement_notification(db, test_user.id, AchievementTypeEnum.HALL_OF_FAME)

        _, kwargs = mock_send.call_args
        assert kwargs["achievement_type"] == "hall_of_fame"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `DATABASE_URL="sqlite:///./test.db" pytest tests/services/test_notifications.py::TestSendAchievementNotification -v`
Expected: FAIL — `AttributeError: module 'src.services.notifications' has no attribute 'send_achievement_notification'`

- [ ] **Step 3: Implement `ACHIEVEMENT_COPY` and `send_achievement_notification`**

Append to `src/services/notifications.py` (add the import too):

```python
from src.models.enums.achievement_enum import AchievementTypeEnum
```

```python
ACHIEVEMENT_COPY: dict[AchievementTypeEnum, tuple[str, str]] = {
    AchievementTypeEnum.FIRST_LIKE: ("Achievement unlocked!", "You liked your first game."),
    AchievementTypeEnum.FIRST_SUBMIT: ("Achievement unlocked!", "You submitted your first game."),
    AchievementTypeEnum.FIVE_UPLOADS: ("Achievement unlocked!", "You've uploaded 5 games."),
    AchievementTypeEnum.TEN_LIKES_ON_UPLOAD: ("Achievement unlocked!", "One of your games hit 10 likes."),
    AchievementTypeEnum.HALL_OF_FAME: ("Hall of Fame!", "Your game has been verified by What's That Game."),
}

_DEFAULT_ACHIEVEMENT_COPY = ("Achievement unlocked!", "You've earned a new achievement.")


def send_achievement_notification(db: Session, user_id: str, achievement_type: AchievementTypeEnum) -> None:
    title, body = ACHIEVEMENT_COPY.get(achievement_type, _DEFAULT_ACHIEVEMENT_COPY)
    send(
        db,
        user_id,
        title,
        body,
        notification_type="achievement",
        data={"achievement_type": achievement_type.value},
        achievement_type=achievement_type.value,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `DATABASE_URL="sqlite:///./test.db" pytest tests/services/test_notifications.py -v`
Expected: 10 passed

- [ ] **Step 5: Write the failing test for the `grant_if_not_exists` hook**

Create `tests/services/test_achievements.py`:

```python
from unittest.mock import patch

from src.models.enums.achievement_enum import AchievementTypeEnum
from src.services.achievements import grant_if_not_exists


class TestGrantNotificationHook:
    def test_sends_notification_for_non_signal_achievement(self, db, test_user):
        with patch("src.services.achievements.notifications.send_achievement_notification") as mock_send:
            granted = grant_if_not_exists(db, test_user.id, AchievementTypeEnum.FIRST_LIKE)

        assert granted is True
        mock_send.assert_called_once_with(db, test_user.id, AchievementTypeEnum.FIRST_LIKE)

    def test_does_not_send_for_signal_only_achievement(self, db, test_user):
        with patch("src.services.achievements.notifications.send_achievement_notification") as mock_send:
            grant_if_not_exists(db, test_user.id, AchievementTypeEnum.SHARE_GAME)

        mock_send.assert_not_called()

    def test_does_not_send_when_already_granted(self, db, test_user):
        grant_if_not_exists(db, test_user.id, AchievementTypeEnum.FIRST_LIKE)
        db.commit()

        with patch("src.services.achievements.notifications.send_achievement_notification") as mock_send:
            granted_again = grant_if_not_exists(db, test_user.id, AchievementTypeEnum.FIRST_LIKE)

        assert granted_again is False
        mock_send.assert_not_called()
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `DATABASE_URL="sqlite:///./test.db" pytest tests/services/test_achievements.py -v`
Expected: FAIL — `mock_send.assert_called_once_with(...)` fails because nothing calls it yet (or `AttributeError` if `achievements.py` doesn't reference `notifications` at all yet).

- [ ] **Step 7: Wire the hook**

Modify `src/services/achievements.py`:

```python
from sqlalchemy.orm import Session

from src.db.tables import UserAchievement
from src.models.enums.achievement_enum import AchievementTypeEnum, SIGNAL_ONLY_ACHIEVEMENTS
from src.services import notifications


def grant_if_not_exists(db: Session, user_id: str, achievement: AchievementTypeEnum) -> bool:
    existing = db.query(UserAchievement).filter_by(
        user_id=user_id, achievement_type=achievement.value
    ).first()
    if existing:
        return False
    db.add(UserAchievement(user_id=user_id, achievement_type=achievement.value))
    if achievement not in SIGNAL_ONLY_ACHIEVEMENTS:
        notifications.send_achievement_notification(db, user_id, achievement)
    return True
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `DATABASE_URL="sqlite:///./test.db" pytest tests/services/test_achievements.py -v`
Expected: 3 passed

- [ ] **Step 9: Run the full existing achievements + favourites + games test suites to confirm no regressions**

This is the critical check for the invariant noted in the spec: these tests use `client_with_auth`/`client_as_second_user`, whose users never register a `PushToken`, so `send()` always takes the `no_token` early-return path — no real Expo call, and the autouse safety net (Task 2) would fail loudly if that assumption were ever violated.

Run: `OPENAI_API_KEY="" DATABASE_URL="sqlite:///./test.db" pytest tests/api/achievements/ tests/api/favourites/ tests/api/games/ -v`
Expected: all pass, zero failures, zero errors from the `block_real_push_notifications` safety net.

- [ ] **Step 10: Commit**

```bash
git add src/services/achievements.py src/services/notifications.py tests/services/test_achievements.py tests/services/test_notifications.py
git commit -m "feat(notifications): hook achievement grants into push notifications"
```

---

### Task 4: Push token registration endpoints

**Files:**
- Create: `src/models/notification_models/__init__.py`
- Create: `src/models/notification_models/push_token.py`
- Create: `src/api/push_tokens.py`
- Modify: `src/main.py` (register router)
- Test: `tests/api/push_tokens/__init__.py`
- Test: `tests/api/push_tokens/test_push_tokens.py`

**Interfaces:**
- Consumes: `src.db.tables.PushToken` (Task 1)
- Produces: `POST /push-tokens/` (upsert), `DELETE /push-tokens/` (scoped to current user's own token)

- [ ] **Step 1: Write the failing tests**

Create `src/models/notification_models/__init__.py` (empty file).

Create `tests/api/push_tokens/__init__.py` (empty file).

Create `tests/api/push_tokens/test_push_tokens.py`:

```python
from src.db.tables import PushToken


class TestRegisterPushToken:
    def test_requires_auth(self, client_no_auth):
        response = client_no_auth.post(
            "/push-tokens/", json={"token": "ExponentPushToken[a]", "platform": "ios"}
        )
        assert response.status_code == 401

    def test_creates_new_token(self, client_with_auth, db, test_user):
        response = client_with_auth.post(
            "/push-tokens/", json={"token": "ExponentPushToken[a]", "platform": "ios"}
        )
        assert response.status_code == 201

        row = db.query(PushToken).filter_by(token="ExponentPushToken[a]").first()
        assert row.user_id == test_user.id
        assert row.platform == "ios"

    def test_upserts_existing_token_to_new_owner(self, client_with_auth, db, second_user, test_user):
        # Seed the token as owned by second_user directly in the DB — do NOT use a second
        # client fixture here. app.dependency_overrides is one dict on one app object; using
        # two client fixtures (e.g. client_with_auth + client_as_second_user) in the same test
        # means the second one's override wins for the whole test body, silently collapsing
        # both "clients" onto the same user and making this test pass vacuously.
        db.add(PushToken(token="ExponentPushToken[shared]", user_id=second_user.id, platform="android"))
        db.commit()

        response = client_with_auth.post(
            "/push-tokens/", json={"token": "ExponentPushToken[shared]", "platform": "ios"}
        )
        assert response.status_code == 200

        rows = db.query(PushToken).filter_by(token="ExponentPushToken[shared]").all()
        assert len(rows) == 1
        assert rows[0].user_id == test_user.id
        assert rows[0].platform == "ios"


class TestDeletePushToken:
    def test_requires_auth(self, client_no_auth):
        response = client_no_auth.request("DELETE", "/push-tokens/", json={"token": "x"})
        assert response.status_code == 401

    def test_deletes_own_token(self, client_with_auth, db, test_user):
        db.add(PushToken(token="ExponentPushToken[mine]", user_id=test_user.id, platform="ios"))
        db.commit()

        response = client_with_auth.request("DELETE", "/push-tokens/", json={"token": "ExponentPushToken[mine]"})
        assert response.status_code == 204
        assert db.query(PushToken).filter_by(token="ExponentPushToken[mine]").first() is None

    def test_does_not_delete_other_users_token(self, client_with_auth, db, second_user):
        db.add(PushToken(token="ExponentPushToken[theirs]", user_id=second_user.id, platform="ios"))
        db.commit()

        response = client_with_auth.request("DELETE", "/push-tokens/", json={"token": "ExponentPushToken[theirs]"})
        assert response.status_code == 204
        assert db.query(PushToken).filter_by(token="ExponentPushToken[theirs]").first() is not None

    def test_nonexistent_token_still_204(self, client_with_auth):
        response = client_with_auth.request("DELETE", "/push-tokens/", json={"token": "ExponentPushToken[nope]"})
        assert response.status_code == 204
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `DATABASE_URL="sqlite:///./test.db" pytest tests/api/push_tokens/ -v`
Expected: FAIL — 404s (route doesn't exist yet) since `src/api/push_tokens.py` and its router registration don't exist.

- [ ] **Step 3: Create the Pydantic models**

Create `src/models/notification_models/push_token.py`:

```python
from pydantic import BaseModel


class PushTokenCreate(BaseModel):
    token: str
    platform: str


class PushTokenDelete(BaseModel):
    token: str
```

- [ ] **Step 4: Create the router**

Create `src/api/push_tokens.py`:

```python
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from src.api.users import get_current_active_user
from src.db.database import get_db
from src.db.tables import PushToken, User
from src.models.notification_models.push_token import PushTokenCreate, PushTokenDelete

router = APIRouter()


@router.post("/")
def register_push_token(
        db: Annotated[Session, Depends(get_db)],
        body: PushTokenCreate,
        current_user: User = Depends(get_current_active_user),
):
    existing = db.query(PushToken).filter(PushToken.token == body.token).first()
    if existing:
        existing.user_id = current_user.id
        existing.platform = body.platform
        db.commit()
        return JSONResponse(status_code=200, content={"status": "ok"})

    db.add(PushToken(token=body.token, user_id=current_user.id, platform=body.platform))
    db.commit()
    return JSONResponse(status_code=201, content={"status": "ok"})


@router.delete("/", status_code=204)
def delete_push_token(
        db: Annotated[Session, Depends(get_db)],
        body: PushTokenDelete,
        current_user: User = Depends(get_current_active_user),
):
    db.query(PushToken).filter(
        PushToken.token == body.token,
        PushToken.user_id == current_user.id,
    ).delete()
    db.commit()
```

- [ ] **Step 5: Register the router**

In `src/main.py`, add `push_tokens` to the import line (line 12):

```python
from src.api import users, games, auth, favourites, metadata, optimisation, search, achievements, aliases, comments, feedback, short_links, photos, push_tokens
```

And add after the `photos` router registration (line 73):

```python
app.include_router(push_tokens.router, prefix="/push-tokens", tags=["push-tokens"])
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `DATABASE_URL="sqlite:///./test.db" pytest tests/api/push_tokens/ -v`
Expected: 7 passed

- [ ] **Step 7: Commit**

```bash
git add src/models/notification_models/__init__.py src/models/notification_models/push_token.py src/api/push_tokens.py src/main.py tests/api/push_tokens/
git commit -m "feat(notifications): add push token registration endpoints"
```

---

### Task 5: Admin game-verify endpoint + `HALL_OF_FAME` grant

**Files:**
- Modify: `src/api/games.py`
- Modify: `src/models/game_models/game.py` (delete dead `GameUpdateAdmin`)
- Test: `tests/api/games/test_games_verify.py` (new file)

**Interfaces:**
- Consumes: `grant_if_not_exists` (existing, now hooked per Task 3), `require_admin` (`src/api/users.py:93`), `map_game_to_read`/`_get_liked_ids` (existing, `src/api/games.py:536-541`)
- Produces: `POST /games/{game_id}/verify` → `GameRead`

- [ ] **Step 1: Confirm `GameUpdateAdmin` really is unused before deleting it**

Run: `grep -rn "GameUpdateAdmin" src/ tests/ --include="*.py"`
Expected: only the definition in `src/models/game_models/game.py`, no other references. If anything else turns up, stop and investigate before proceeding — do not delete it blind.

- [ ] **Step 2: Write the failing tests**

Create `tests/api/games/test_games_verify.py`:

```python
import uuid

from src.db.tables import Game, UserAchievement
from src.models.enums.achievement_enum import AchievementTypeEnum
from tests.api.games.helper import create_public_game


def _seed_game_owned_by(db, contributor_id: str) -> Game:
    game = Game(
        id=str(uuid.uuid4()),
        name="Contributor's Game",
        description="desc",
        game_type="Card",
        min_players=2,
        max_players=6,
        duration="30-45 minutes",
        objective="win",
        setup="setup",
        rules="rules",
        is_public=True,
        contributor_id=contributor_id,
    )
    db.add(game)
    db.commit()
    return game


class TestVerifyGame:
    def test_requires_admin(self, client_with_auth):
        game = create_public_game(client_with_auth)
        response = client_with_auth.post(f"/games/{game['id']}/verify")
        assert response.status_code == 403

    def test_requires_auth(self, client_no_auth):
        response = client_no_auth.post("/games/some-id/verify")
        assert response.status_code == 401

    def test_missing_game_is_404(self, client_as_admin):
        response = client_as_admin.post("/games/does-not-exist/verify")
        assert response.status_code == 404

    def test_sets_verified_flag(self, client_as_admin, db, test_user):
        # Only ONE client fixture per test — app.dependency_overrides is one dict on one app
        # object, so mixing client_with_auth + client_as_admin in the same test makes the
        # later fixture's auth override win for the whole test body, silently collapsing both
        # "clients" onto admin_user. Seed the game directly in the DB instead of creating it
        # via a second client.
        game = _seed_game_owned_by(db, test_user.id)
        response = client_as_admin.post(f"/games/{game.id}/verify")
        assert response.status_code == 200
        assert response.json()["is_whats_that_game_certified"] is True

    def test_grants_hall_of_fame_to_contributor(self, client_as_admin, db, test_user):
        game = _seed_game_owned_by(db, test_user.id)
        client_as_admin.post(f"/games/{game.id}/verify")

        achievement = db.query(UserAchievement).filter_by(
            user_id=test_user.id,
            achievement_type=AchievementTypeEnum.HALL_OF_FAME.value,
        ).first()
        assert achievement is not None

    def test_idempotent_on_repeat_verify(self, client_as_admin, db, test_user):
        game = _seed_game_owned_by(db, test_user.id)
        client_as_admin.post(f"/games/{game.id}/verify")
        client_as_admin.post(f"/games/{game.id}/verify")

        count = db.query(UserAchievement).filter_by(
            user_id=test_user.id,
            achievement_type=AchievementTypeEnum.HALL_OF_FAME.value,
        ).count()
        assert count == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `DATABASE_URL="sqlite:///./test.db" pytest tests/api/games/test_games_verify.py -v`
Expected: FAIL — 404 Not Found (route doesn't exist).

- [ ] **Step 4: Add the endpoint**

In `src/api/games.py`, update the import from `src.api.users` (currently `from src.api.users import get_current_active_user, get_current_user_optional`) to also import `require_admin`:

```python
from src.api.users import get_current_active_user, get_current_user_optional, require_admin
```

Add the new endpoint after `report_game` (after line 284, before the `# READ` comment on line 287):

```python
@protected_router.post("/{game_id}/verify", response_model=GameRead, status_code=200,
                       responses={403: {"description": "Admin only"}, 404: {"description": "Game not found"}})
def verify_game(
        db: Annotated[Session, Depends(get_db)],
        game_id: str,
        current_user: User = Depends(require_admin),
):
    db_game = db.query(Game).filter(Game.id == game_id).first()
    if not db_game:
        raise GAME_NOT_FOUND_EXCEPTION

    db_game.is_whats_that_game_verified = True
    grant_if_not_exists(db, db_game.contributor_id, AchievementTypeEnum.HALL_OF_FAME)
    db.commit()
    db.refresh(db_game)

    liked_ids = _get_liked_ids(db, current_user.id)
    return map_game_to_read(db_game, liked_ids)
```

- [ ] **Step 5: Delete the dead `GameUpdateAdmin` model**

In `src/models/game_models/game.py`, remove:

```python
class GameUpdateAdmin(GameUpdate):
    is_whats_that_game_certified: Optional[bool] = None
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `DATABASE_URL="sqlite:///./test.db" pytest tests/api/games/test_games_verify.py -v`
Expected: 6 passed

- [ ] **Step 7: Run the full games test suite to confirm no regressions**

Run: `OPENAI_API_KEY="" DATABASE_URL="sqlite:///./test.db" pytest tests/api/games/ -v`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add src/api/games.py src/models/game_models/game.py tests/api/games/test_games_verify.py
git commit -m "feat(notifications): add admin game-verify endpoint granting HALL_OF_FAME"
```

---

### Task 6: Admin notifications endpoint (single-user + broadcast)

**Files:**
- Create: `src/models/notification_models/admin_notification.py`
- Create: `src/api/admin_notifications.py`
- Modify: `src/main.py` (register router)
- Test: `tests/api/admin_notifications/__init__.py`
- Test: `tests/api/admin_notifications/test_admin_notifications.py`

**Interfaces:**
- Consumes: `notifications.send()` (Task 2), `require_admin` (`src/api/users.py:93`), `src.db.database.SessionLocal`
- Produces: `POST /admin/notifications` — `{target: "user"|"broadcast", user_id?, game_id?, title, body}` → `{"status": "sent"|"queued"}`

- [ ] **Step 1: Write the failing tests**

Create `src/models/notification_models/admin_notification.py` first (models needed before tests can even construct request bodies meaningfully, but the route itself won't exist yet — this is fine, tests will still fail on 404/connection at the route level):

```python
from typing import Literal, Optional

from pydantic import BaseModel, model_validator


class AdminNotificationRequest(BaseModel):
    target: Literal["user", "broadcast"]
    user_id: Optional[str] = None
    game_id: Optional[str] = None
    title: str
    body: str

    @model_validator(mode="after")
    def check_user_id_present_for_user_target(self):
        if self.target == "user" and not self.user_id:
            raise ValueError("user_id is required when target is 'user'")
        return self
```

Create `tests/api/admin_notifications/__init__.py` (empty file).

Create `tests/api/admin_notifications/test_admin_notifications.py`:

```python
from unittest.mock import patch

from src.db.tables import Notification, User


class TestSendToUser:
    def test_requires_admin(self, client_with_auth, test_user):
        response = client_with_auth.post(
            "/admin/notifications",
            json={"target": "user", "user_id": test_user.id, "title": "Hi", "body": "There"},
        )
        assert response.status_code == 403

    def test_requires_auth(self, client_no_auth):
        response = client_no_auth.post(
            "/admin/notifications",
            json={"target": "user", "user_id": "x", "title": "Hi", "body": "There"},
        )
        assert response.status_code == 401

    def test_missing_user_id_for_user_target_is_422(self, client_as_admin):
        response = client_as_admin.post(
            "/admin/notifications", json={"target": "user", "title": "Hi", "body": "There"}
        )
        assert response.status_code == 422

    def test_unknown_user_id_is_404(self, client_as_admin):
        response = client_as_admin.post(
            "/admin/notifications",
            json={"target": "user", "user_id": "does-not-exist", "title": "Hi", "body": "There"},
        )
        assert response.status_code == 404

    def test_sends_synchronously_and_logs_notification_with_game_id(self, client_as_admin, db, test_user):
        response = client_as_admin.post(
            "/admin/notifications",
            json={"target": "user", "user_id": test_user.id, "game_id": "g1", "title": "Hi", "body": "There"},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "sent"}

        note = db.query(Notification).filter_by(user_id=test_user.id).first()
        assert note.status == "no_token"  # test_user has no push token registered
        assert note.data == '{"game_id": "g1"}'


class TestBroadcast:
    def test_requires_admin(self, client_with_auth):
        response = client_with_auth.post(
            "/admin/notifications", json={"target": "broadcast", "title": "Hi", "body": "There"}
        )
        assert response.status_code == 403

    def test_dispatches_via_background_task_and_reaches_active_users(
        self, client_as_admin, db, test_user, second_user
    ):
        # The background task opens its own SessionLocal() in production (separate lifecycle
        # from the request-scoped `db`). In tests we redirect it to the same per-test `db`
        # session so we can assert on real behavior, and neutralize db.close() so the task's
        # cleanup doesn't tear down the session the test still needs afterward.
        with patch("src.api.admin_notifications.SessionLocal", return_value=db), \
             patch.object(db, "close"):
            response = client_as_admin.post(
                "/admin/notifications",
                json={"target": "broadcast", "title": "Announcement", "body": "New feature!"},
            )
        assert response.status_code == 202
        assert response.json() == {"status": "queued"}

        notified_user_ids = {
            n.user_id for n in db.query(Notification).filter_by(title="Announcement").all()
        }
        assert test_user.id in notified_user_ids
        assert second_user.id in notified_user_ids

    def test_excludes_inactive_users(self, client_as_admin, db, test_user):
        inactive = User(
            id="inactive-user-id", firstname="I", lastname="U", username="inactiveuser",
            email="inactive@example.com", hashed_password="x", is_active=False,
        )
        db.add(inactive)
        db.commit()

        with patch("src.api.admin_notifications.SessionLocal", return_value=db), \
             patch.object(db, "close"):
            client_as_admin.post(
                "/admin/notifications",
                json={"target": "broadcast", "title": "Announcement2", "body": "New feature!"},
            )

        notified_user_ids = {
            n.user_id for n in db.query(Notification).filter_by(title="Announcement2").all()
        }
        assert "inactive-user-id" not in notified_user_ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `DATABASE_URL="sqlite:///./test.db" pytest tests/api/admin_notifications/ -v`
Expected: FAIL — 404s (route doesn't exist) / `ModuleNotFoundError` for `src.api.admin_notifications`.

- [ ] **Step 3: Create the router**

Create `src/api/admin_notifications.py`:

```python
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from src.api.users import require_admin
from src.db.database import SessionLocal, get_db
from src.db.tables import User
from src.models.notification_models.admin_notification import AdminNotificationRequest
from src.services import notifications

router = APIRouter()


def _broadcast_task(title: str, body: str, game_id: str | None) -> None:
    db = SessionLocal()
    try:
        data = {"game_id": game_id} if game_id else None
        user_ids = [row.id for row in db.query(User.id).filter(User.is_active.is_(True)).all()]
        for user_id in user_ids:
            notifications.send(db, user_id, title, body, notification_type="custom", data=data)
        db.commit()
    finally:
        db.close()


@router.post("/notifications")
def send_admin_notification(
        db: Annotated[Session, Depends(get_db)],
        body: AdminNotificationRequest,
        background_tasks: BackgroundTasks,
        current_user: User = Depends(require_admin),
):
    data = {"game_id": body.game_id} if body.game_id else None

    if body.target == "user":
        target_user = db.query(User).filter(User.id == body.user_id).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")
        notifications.send(db, body.user_id, body.title, body.body, notification_type="custom", data=data)
        db.commit()
        return JSONResponse(status_code=200, content={"status": "sent"})

    background_tasks.add_task(_broadcast_task, body.title, body.body, body.game_id)
    return JSONResponse(status_code=202, content={"status": "queued"})
```

- [ ] **Step 4: Register the router**

In `src/main.py`, add `admin_notifications` to the import line (line 12, now including `push_tokens` from Task 4):

```python
from src.api import users, games, auth, favourites, metadata, optimisation, search, achievements, aliases, comments, feedback, short_links, photos, push_tokens, admin_notifications
```

Add after the `push_tokens` router registration:

```python
app.include_router(admin_notifications.router, prefix="/admin", tags=["admin"])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `DATABASE_URL="sqlite:///./test.db" pytest tests/api/admin_notifications/ -v`
Expected: 7 passed

- [ ] **Step 6: Run the full test suite**

Run: `OPENAI_API_KEY="" DATABASE_URL="sqlite:///./test.db" pytest -v`
Expected: all pass, no regressions anywhere in the suite.

- [ ] **Step 7: Commit**

```bash
git add src/models/notification_models/admin_notification.py src/api/admin_notifications.py src/main.py tests/api/admin_notifications/
git commit -m "feat(notifications): add admin single-user and broadcast notification endpoint"
```

---

## Post-plan verification

After Task 6, run the complete suite one more time and confirm the count is sane relative to the pre-existing baseline (313 tests passed before this feature, per project memory):

```bash
OPENAI_API_KEY="" DATABASE_URL="sqlite:///./test.db" pytest -v 2>&1 | tail -20
```

Expect roughly 313 + 4 (Task1) + 4 (Task2) + 2 (Task3 notifications) + 3 (Task3 achievements hook) + 7 (Task4) + 6 (Task5) + 7 (Task6) ≈ 346 tests, all passing, zero real network calls (the Task 2 safety net would surface those as `AssertionError` failures, not silent successes).
