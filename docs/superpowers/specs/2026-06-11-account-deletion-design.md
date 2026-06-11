# Account Deletion Design

## Overview

Fix the known `DELETE /users/{user_id}` 500 bug and implement GDPR-compliant two-stage soft-delete.
The 500 occurs because `Game.contributor_id` is `nullable=False` with no cascade, so
`db.delete(user)` raises `IntegrityError` for any user with games.

---

## Goals

- Fix the 500 crash on account deletion
- Fulfil GDPR/Play Store deletion promise
- Give users a 30-day recovery window before data is permanently erased
- Keep all existing queries working unchanged (no NULL contributor handling)

---

## Architecture

### Two stages

**Stage 1 — Deactivation (Day 0, user-triggered):**
Set `is_active=False` and `deletion_requested_at=now()`. Blocks login immediately. User has
30 days to reactivate. No data is deleted at this point.

**Stage 2 — Purge (Day 30, automated):**
APScheduler daily sweep finds users past the 30-day window and erases PII, anonymises public
games via a `deleted-user` placeholder account, and hard-deletes the user row.

Always soft (single code path). No "immediate delete" option.

---

## DB Schema Change

One new column on `users` (no Alembic — run manually on Railway prod before deploy):

```sql
ALTER TABLE users ADD COLUMN deletion_requested_at TIMESTAMP;
```

`is_active` already exists and is used for login blocking. `deletion_requested_at` is the
30-day clock and distinguishes a deleted account from a manually-deactivated one.

---

## Deleted-User Placeholder Account

A permanent seeder creates one fixed placeholder user. All public games by purged users are
reassigned to this account.

- Fixed UUID: `00000000-0000-0000-0000-000000000001` (stored in `src/utils/config.py` as
  `DELETED_USER_ID`)
- `username="deleted-user"`, `firstname="Deleted"`, `lastname="User"`,
  `email="deleted@internal"`, `is_active=False`, no password, no OAuth
- Seeder: `scripts/seed_deleted_user.py` — idempotent (`INSERT ... WHERE NOT EXISTS`), safe
  to re-run
- Must be seeded in Railway prod before any purge runs

Frontend renders contributor `username="deleted-user"` as "Deleted user" wherever contributor
name appears.

---

## Endpoints

### `DELETE /users/me` (replaces `DELETE /users/{user_id}`)

Auth required (own account only). Sets `is_active=False`, `deletion_requested_at=now()`.

**Response 200:**
```json
{
  "message": "Account deactivated. You have 30 days to reactivate before your data is permanently deleted."
}
```

No data is deleted. No cascade. The 500 is fixed because `db.delete(user)` is never called.

---

### `POST /users/reactivate`

Unauthenticated (user cannot log in while inactive). For password-based accounts only.

**Request body:**
```json
{"email": "user@example.com", "password": "plaintextpassword"}
```

**Logic:**
1. Find user by email
2. Verify password
3. Check `is_active=False AND deletion_requested_at IS NOT NULL AND deletion_requested_at > now() - 30 days`
4. Set `is_active=True`, clear `deletion_requested_at`
5. Return new access token (same shape as `POST /auth/token`)

**Error responses:**
- `400` if credentials invalid, account not in deletion window, or already past 30 days
- `404` if email not found (after purge, user row is gone)

---

### OAuth reactivation

No dedicated endpoint. When an OAuth user successfully authenticates via
`POST /auth/oauth/google/token`, the auth handler checks:

```
if user.is_active is False
    and user.deletion_requested_at is not None
    and user.deletion_requested_at > now() - 30 days:
        reactivate (set is_active=True, clear deletion_requested_at)
```

Then proceeds with normal login. Past 30 days, user row is gone — OAuth handler creates a new
account (existing behaviour).

---

## Purge Service

### `src/services/purge.py`

`run_purge(db: Session)` function:

1. Query: `User WHERE is_active=False AND deletion_requested_at <= now() - 30 days`
2. For each user:
   a. `UPDATE games SET contributor_id=DELETED_USER_ID WHERE contributor_id=user.id AND is_public=True`
   b. Hard-delete private games (`DELETE FROM games WHERE contributor_id=user.id AND is_public=False`) — cascade deletes `GameEquipment`, `GameSetting`, `GameAlias`, `GameComment`, `CommentLike`
   c. `DELETE FROM user_favourites WHERE user_id=user.id`
   d. `DELETE FROM user_achievements WHERE user_id=user.id`
   e. `DELETE FROM game_reports WHERE reporter_id=user.id`
   f. `UPDATE game_comments SET user_id=DELETED_USER_ID WHERE user_id=user.id` (comments anonymised, not deleted)
   g. `UPDATE game_aliases SET suggested_by=DELETED_USER_ID WHERE suggested_by=user.id AND status='approved'`
   h. `DELETE FROM game_aliases WHERE suggested_by=user.id AND status != 'approved'`
   i. `db.delete(user)` — now safe, no remaining FK references
3. `db.commit()` after each user (isolated, partial purge acceptable)

---

## Scheduler

### `src/core/scheduler.py`

```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
```

### `src/main.py` lifespan

`Base.metadata.create_all` and scheduler start/shutdown move into a `lifespan` context
manager:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    scheduler.add_job(lambda: run_purge_with_db(), "cron", hour=0, minute=0)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan, ...)
```

`run_purge_with_db` opens a fresh `SessionLocal` db session, calls `run_purge(db)`, closes it.

`apscheduler` added to `requirements.txt`.

---

## Data Handling at Purge

| Table | Action |
|---|---|
| `games` (public) | `contributor_id` → `DELETED_USER_ID` |
| `games` (private) | Hard-delete (cascade: equipment, settings, aliases, comments) |
| `user_favourites` | Delete all rows for user |
| `user_achievements` | Delete all rows for user |
| `game_reports` | Delete all rows where `reporter_id = user.id` |
| `game_comments` | `user_id` → `DELETED_USER_ID` (comment preserved, anonymised) |
| `game_aliases` (approved) | `suggested_by` → `DELETED_USER_ID` (alias preserved) |
| `game_aliases` (pending/rejected) | Delete |
| `users` | Hard-delete after above |

---

## Privacy Policy

Two files require §8 (Data Retention) update:

1. `PRIVACY_POLICY.md` in this repo
2. `index.html` in `maxswaine/WhatsThatGamePrivacyPolicy` (branch `main`, live at
   `https://maxswaine.github.io/WhatsThatGamePrivacyPolicy/`)

Updated retention text: accounts deactivated on deletion request; PII and private data
permanently erased after 30-day recovery window; public game contributions anonymised and
retained; contact `whatsthatgameteam@gmail.com` for erasure requests.

---

## Out of Scope (This Feature)

- `delete-account.html` web page in Pages repo (store publishing task)
- Play Console Data Safety form update
- Login rate-limiting on `/auth/token`
- Railway EU region verification

---

## Tests

| Scenario | Expected |
|---|---|
| User with games calls `DELETE /users/me` | 200, `is_active=False`, no 500 |
| User without games calls `DELETE /users/me` | 200, `is_active=False` |
| Inactive user calls `GET /games/mine` | 403 (blocked by `get_current_active_user`) |
| Reactivate within 30 days (password) | 200, token returned, `is_active=True` |
| Reactivate after 30 days | 400 or 404 (user purged) |
| OAuth login while in deletion window | Reactivates, returns token |
| `run_purge` with user past 30 days | Public games reassigned, private deleted, comments anonymised, user row gone |
| `run_purge` with user inside 30 days | No action |
| Seeder run twice | No duplicate placeholder user |
