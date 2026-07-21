# Notifications — Design Spec

Status: approved, pending implementation
Branch: `feature/pre-launch-features`

## 1. Purpose

Push notifications for the mobile app, delivered via Expo Push Service. Two triggers in v1:

1. **Achievement grants** (server-computed types only — see §5) push automatically when earned.
2. **Admin-sent messages** — single-user or broadcast — via an admin-only endpoint.

Also introduces a new achievement: `HALL_OF_FAME`, granted when a game receives What's That Game verification (via a
new admin-only verify endpoint, since no such endpoint currently exists).

Out of scope for v1: in-app notification inbox / `GET /notifications` (table is written on every send so no data is
lost when this is added later), email notifications, user-configurable notification preferences.

## 2. Architecture

```
push_tokens table  <--upsert/delete--  POST/DELETE /push-tokens
                                                |
                                                v
grant_if_not_exists() ---(on new grant)---> NotificationService.send() ---> Expo Push API
       ^                                          |
       |                                          v
POST /games/{id}/verify (admin)          notifications table (log row)
       |
POST /admin/notifications (admin) -------^
```

Single send path: every notification — achievement or admin-sent — goes through one
`src/services/notifications.py::send()` function. No ad-hoc Expo API calls elsewhere.

## 3. Data model

Added to `src/db/tables.py`:

```python
class PushToken(Base):
    __tablename__ = "push_tokens"
    token = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = Column(String, nullable=False)  # "ios" | "android"
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String, nullable=False)  # "achievement" | "custom"
    title = Column(String, nullable=False)
    body = Column(String, nullable=False)
    data = Column(String, nullable=True)  # JSON string, e.g. {"game_id": "..."} or {"achievement_type": "..."}
    achievement_type = Column(String, nullable=True)
    status = Column(String, nullable=False)  # "sent" | "failed" | "no_token"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
```

`token` is the PK (not `(user_id, token)`) so re-registering the same physical device under a different account
(logout/login as a different user) cleanly reassigns ownership via upsert rather than accumulating stale rows. No
uniqueness constraint on `user_id` — one user can have multiple tokens (multiple devices).

No Alembic — both tables auto-created by `create_all` on next deploy, per project convention.

### Enum change

`src/models/enums/achievement_enum.py`:

```python
class AchievementTypeEnum(str, Enum):
    FIRST_LIKE = "first_like"
    FIRST_SUBMIT = "first_submit"
    SHARE_GAME = "share_game"
    FIVE_UPLOADS = "five_uploads"
    TEN_LIKES_ON_UPLOAD = "ten_likes_on_upload"
    GIVE_FEEDBACK = "give_feedback"
    COMPLETE_TUTORIAL = "complete_tutorial"
    HALL_OF_FAME = "hall_of_fame"  # new


SIGNAL_ONLY_ACHIEVEMENTS = {
    AchievementTypeEnum.SHARE_GAME,
    AchievementTypeEnum.GIVE_FEEDBACK,
    AchievementTypeEnum.COMPLETE_TUTORIAL,
}
```

`HALL_OF_FAME` is **not** added to `SIGNAL_ONLY_ACHIEVEMENTS` — it's server-granted (via the verify endpoint, not a
client signal) and should push like the other server-granted types.

## 4. Service layer

`src/services/notifications.py`:

```python
def send(
    db: Session,
    user_id: str,
    title: str,
    body: str,
    *,
    type: str = "custom",
    data: dict | None = None,
    achievement_type: str | None = None,
) -> None:
```

Behavior:

1. Look up all `PushToken` rows for `user_id`.
2. If none: write a `Notification` row with `status="no_token"`, return. No-op, no exception.
3. Otherwise call the Expo push API via `exponent-server-sdk` (`PushClient().publish_multiple(...)`), one message per
   token.
4. Write one `Notification` row per call to `send()` (not per token) — `status="sent"` if the Expo call succeeded,
   `status="failed"` if it raised.
5. Inspect ticket/receipt responses for `DeviceNotRegistered` errors; delete the corresponding `PushToken` row(s).
6. Never raises. Every exception from the Expo SDK is caught and swallowed — matches the existing
   `try/except: pass` best-effort convention used for embeddings in `games.py`. A push failure must never fail the
   underlying action (vote, achievement grant, admin call).

`exponent-server-sdk` chosen over raw `requests` calls to match the existing convention of using vendor SDKs for
external APIs (`email.py` uses the `resend` SDK the same way). It also handles chunking automatically (Expo's API
caps at 100 messages/request).

### Hook point

`src/services/achievements.py::grant_if_not_exists` — the single existing choke point for all achievement grants —
gets one addition: after `db.add(UserAchievement(...))`, if `achievement not in SIGNAL_ONLY_ACHIEVEMENTS`, call
`notifications.send(...)` with a title/body derived from the achievement type. This covers every existing call site
(`favourites.py`, `games.py` x3, `achievements.py` signal endpoint) plus the new `HALL_OF_FAME` grant, with zero
changes needed at any call site.

**Accepted tradeoff (explicit, not accidental):** `exponent-server-sdk` is synchronous (`requests`-based), so this
hook makes a synchronous external HTTP call inside the request/response cycle for every non-signal-only achievement
grant — including `TEN_LIKES_ON_UPLOAD`, which fires from the upvote endpoint (`games.py`), a higher-frequency path
than game create/update. This mirrors the existing inline embedding call in `games.py` (`try/except: pass`,
synchronous, best-effort) — same pattern, same convention. Chosen over the alternative (hooking at each API call
site with `BackgroundTasks` instead, so `send()` isn't inline) because that alternative loses the
"zero call-site changes" property that makes this hook point valuable. If upvote-path latency becomes a real
problem post-launch, revisit by moving the hook to the API layer with `BackgroundTasks` — not in this feature.

Same tradeoff has a correctness facet, not just latency: the hook fires before the caller's `db.commit()`. If the
caller's transaction later rolls back (e.g. a later step in the same request fails), the `UserAchievement` and
`Notification` rows roll back with it — DB stays consistent — but the Expo push already left the building and can't
be un-sent. A rolled-back grant can still produce a delivered push. Low-probability, accepted for v1 under the same
best-effort convention as the rest of this hook; not fixed here.

Title/body copy per achievement type lives in a small dict in `notifications.py` (e.g.
`{"first_like": ("Achievement unlocked!", "You liked your first game.")}`) — implementer fills in exact copy per
achievement, not user-facing-critical enough to need sign-off here.

## 5. Endpoints

All under existing routers (`push_tokens`/`notifications` in a new `src/api/push_tokens.py` + admin bits added to
`src/api/games.py` and a new `src/api/admin_notifications.py`, or wherever fits existing router conventions —
implementer's call during planning).

### `POST /push-tokens` (auth required)

Request:
```json
{"token": "ExponentPushToken[xxxx]", "platform": "ios"}
```
Response: `201` (created) or `200` (updated), empty body or `{"status": "ok"}`. Upserts on `token`.

### `DELETE /push-tokens` (auth required)

Request:
```json
{"token": "ExponentPushToken[xxxx]"}
```
Response: `204`. No-op (still `204`) if token doesn't exist.

### `POST /games/{game_id}/verify` (admin only)

No request body. Sets `Game.is_whats_that_game_verified = True`, grants `HALL_OF_FAME` to
`db_game.contributor_id` (via `grant_if_not_exists`, idempotent — repeat calls are a no-op on the achievement and
don't re-notify), returns updated `GameRead`.

Errors: `403` if `current_user.role != Role.admin` (reuse `FORBIDDEN_EXCEPTION`), `404` if game not found (reuse
`GAME_NOT_FOUND_EXCEPTION`).

Note: `GameUpdateAdmin` (`src/models/game_models/game.py`) is currently dead code — never wired to any endpoint. It
gets deleted as part of this feature since this dedicated endpoint replaces its purpose.

### `POST /admin/notifications` (admin only)

Request:
```json
{"target": "user", "user_id": "...", "game_id": "...", "title": "...", "body": "..."}
```
or
```json
{"target": "broadcast", "game_id": "...", "title": "...", "body": "..."}
```
`game_id` is optional in both cases — when present, it's passed through as `data={"game_id": game_id}` on the
notification so the app can deep-link on tap (this is the "custom nudge → game detail" flow from the FE design).

Response: `202 Accepted`, `{"status": "queued"}` for broadcast; `200`, `{"status": "sent"}` for single-user (sent
synchronously since it's one call).

`target="user"` sends synchronously inline. `target="broadcast"` fans out via FastAPI `BackgroundTasks` — iterates
`User` rows where `is_active` is true (excludes soft-deleted/placeholder accounts) and calls `send()` per user — to
avoid a slow/timing-out request as the user base grows.

**Implementation note (verify during planning, don't assume):** the background task must not reuse the
request-scoped `db` session from `Depends(get_db)` — by the time a `BackgroundTasks` callback runs, that session may
already be closed/closing depending on FastAPI's teardown ordering. The task should open its own `SessionLocal()`
and close it when done. Confirm this against the FastAPI/SQLAlchemy versions in use before writing the plan; don't
carry the request session in on faith.

**Known tradeoffs, accepted for v1 (not fixed here):** broadcast calls `send()` once per user rather than batching
through Expo's 100-per-request chunking, so it doesn't get that efficiency at broadcast fan-out time (the SDK still
chunks within a single `send()` call, which only ever targets one user's tokens — this only matters if/when
broadcast volume grows large enough to matter). Broadcast also writes a `no_token` row for every tokenless active
user on every send, which is minor `notifications` table bloat at today's user counts — revisit if it becomes an
issue.

Errors: `403` if not admin, `422` if `target="user"` and `user_id` missing, `404` if `user_id` doesn't exist.

## 6. Error handling

| Scenario | Behavior |
|---|---|
| User has no push token | `send()` writes `status="no_token"` row, returns silently. Caller (vote, achievement grant, admin call) unaffected. |
| Expo API call fails (network, 4xx/5xx) | `status="failed"` row written, exception swallowed. Caller unaffected. |
| Expo ticket/receipt reports `DeviceNotRegistered` | Corresponding `PushToken` row deleted. |
| Admin verify on already-verified game | Idempotent — `is_whats_that_game_verified` stays `True`, `grant_if_not_exists` returns `False` (already has it), no duplicate notification. |

## 7. Testing

All tests mock the Expo SDK client — no real network calls.

- `notifications.send()`: writes correct row for sent/failed/no_token; prunes token on `DeviceNotRegistered`; never
  raises even when the mocked client raises.
- Achievement hook: `grant_if_not_exists` calls `send()` for non-signal-only types, does not call it for
  `SIGNAL_ONLY_ACHIEVEMENTS` types (existing no-push behavior for `share_game`/`give_feedback`/`complete_tutorial`
  unchanged); does not call it when the achievement already existed (no re-notify).

  **Invariant to preserve, not just a test detail:** hooking `send()` into `grant_if_not_exists` means every
  existing achievement test (favourites, games x3) now routes through it too. That's safe only because `send()`
  early-returns with `status="no_token"` when the calling user has no registered `PushToken` — so no real Expo call
  fires from those pre-existing tests. Shared test fixtures/users must not register push tokens by default, or
  ~5 existing green tests silently turn into live Expo network calls. State this explicitly in the plan so it's
  preserved deliberately, not discovered later.
- `POST /games/{id}/verify`: 403 non-admin, 404 missing game, grants `HALL_OF_FAME` once and is idempotent on repeat
  calls, triggers one `send()` call.
- `POST /admin/notifications`: 403 non-admin, single-user path calls `send()` synchronously, broadcast path is
  dispatched via `BackgroundTasks` (assert via FastAPI's background-task test hooks, not a real sleep/wait), 404 for
  unknown `user_id`, `game_id` (when provided) flows into the written `Notification.data`, broadcast excludes
  inactive users.

  **Caveat to design around, not just note:** `TestClient` executes `BackgroundTasks` synchronously in-process
  within the test's own rolled-back transaction, which will make a broadcast test pass even if the production
  session-lifetime handling described in §5 is wrong (e.g. task reuses a closed request-scoped session). A passing
  test here is not sufficient evidence the background-task session pattern is correct — verify the actual session
  construction (fresh `SessionLocal()`, not the injected `db`) by code inspection, not just by the test suite being
  green.
- `POST`/`DELETE /push-tokens`: upsert semantics (same token twice from same user updates, not duplicates), auth
  required, delete removes only the specified token/row, delete of nonexistent token is `204` not `404`.

## 8. Frontend Integration

Base URL / auth: same JWT bearer or httponly cookie auth as all other protected endpoints.

### Register token — `POST /push-tokens`

Request:
```json
{"token": "ExponentPushToken[xxxx]", "platform": "ios"}
```
`platform` is `"ios"` or `"android"`. Call on login/launch after `getExpoPushTokenAsync()`, and again whenever Expo's
token-refresh listener fires (same endpoint — upsert).

Response: `200`/`201`, empty or `{"status": "ok"}`.

### Deregister token — `DELETE /push-tokens`

Request:
```json
{"token": "ExponentPushToken[xxxx]"}
```
Call on logout. Response: `204`.

### Admin verify a game — `POST /games/{game_id}/verify`

Admin-only (requires `role: admin` on the authenticated user — same 403 semantics as other admin-gated endpoints in
this API). No request body. Response: full `GameRead` with `is_whats_that_game_verified: true`.

### Admin send notification — `POST /admin/notifications`

Admin-only.
```json
{"target": "user", "user_id": "...", "game_id": "...", "title": "...", "body": "..."}
```
```json
{"target": "broadcast", "game_id": "...", "title": "...", "body": "..."}
```
`game_id` is optional in both — omit it for a plain message with no deep-link target.

Response: `{"status": "sent"}` (200, user target) or `{"status": "queued"}` (202, broadcast target — fire-and-forget,
no completion callback).

### Push payload shape (what arrives on-device via Expo)

Notification `data` field (used for deep-linking on tap):

- Achievement type: `{"achievement_type": "hall_of_fame"}` → navigate to Achievements screen.
- Custom/admin type: `{"game_id": "..."}` if relevant, else `{}` → navigate to game detail if `game_id` present,
  else no navigation (just dismiss).

`type` field on the notification itself is `"achievement"` or `"custom"` — FE can use this to pick icon/style before
even reading `data`.

### Not included in v1

No `GET /notifications` (list/unread-count) endpoint — the `notifications` table exists and is populated, but there
is no inbox UI yet per current scope. This is a natural follow-up feature once FE builds that screen; no backend
migration needed to add it later (table already has everything needed).

No user-facing opt-out/preferences endpoint in v1.
