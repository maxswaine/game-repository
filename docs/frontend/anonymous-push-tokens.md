# Anonymous Push Tokens — Frontend Integration

## Overview

The app asks for push permission straight after the tutorial, before the user has an account.
`POST /push-tokens/` required auth, so that call 401'd and the token was never stored: the OS showed
notifications as enabled and the backend had no row. iOS has been in this state since push shipped;
on Android it was masked by the missin FCM config.

Three changes, all additive:

1. **`POST /push-tokens/` and `DELETE /push-tokens/` now take *optional* auth.** With a JWT the row is
   owned by that user, without one it is an anonymous device row.
2. **`PushTokenCreate` gains `device_id?: string`** — client-generated, stable per install.
3. **`POST /admin/notifications` gains `audience?: "users" | "devices" | "all"`**, default `"users"`.

Backend is on branch `feature/record-force-submitted` (`src/db/tables.py`, `src/api/push_tokens.py`,
`src/api/admin_notifications.py`, `src/services/notifications.py`, plus the models). **Not merged, not
deployed.**

## ⚠️ Needs a manual migration BEFORE the deploy

`scripts/migrate_anonymous_push_tokens.sql`. `device_id` is an ordinary mapped column, so every
`SELECT` of `push_tokens` emits it — if the deploy lands first, every notification path fails with
`UndefinedColumn` until the migration runs. Both statements are backward compatible with the
currently-deployed code, so running the SQL early is safe and running it late is an outage.

## What the app needs to do

Nothing, to keep working — builds ≤ 1.1.2 send `{token, platform}` with a JWT and behave exactly as
before. `device_id` is optional and auth is still accepted.

To actually fix signed-out registration:

1. Generate a `device_id` once per install (UUID in `expo-secure-store`) and send it on register.
2. Drop the assumption in `registerForPushNotifications()` that a session is required — the
   tutorial-completion path at `src/navigation/index.tsx:324-331` can now register successfully.
3. Keep calling `DELETE /push-tokens/` on sign-out and on the Settings toggle, unchanged.

`device_id` is what keeps one row per device across sign-in and across Expo token rotation. Without it
the device still works, but a rotated token can leave a stale duplicate row behind.

## Contract

### `POST /push-tokens/`

```ts
{ token: string, platform: string, device_id?: string }
```

Auth optional. `201` on insert, `200` on update, `400` if `token` is not an Expo push token.

| Request | Result |
|---|---|
| No JWT | Row stored with `user_id = null` |
| JWT | Row stored/claimed for that user |
| JWT, token already anonymous | That row is claimed — no second row |
| No JWT, token already owned | Owner is **kept**, not stripped |
| Any, with `device_id` | Other rows for that `device_id` are removed — one row per device |

### `DELETE /push-tokens/`

```ts
{ token: string }
```

Auth optional, always `204`. An authenticated caller can delete their own token or an unclaimed one; an
unauthenticated caller can only delete an unclaimed one.

The row is **deleted**, not re-anonymised. The app uses this same call for sign-out and for the Settings
notifications toggle and the backend cannot tell them apart — nulling `user_id` would leave someone who
explicitly turned notifications off still receiving broadcasts. The cost is that signing out drops the
device's anonymous subscription; the next launch re-registers it.

### `POST /admin/notifications`

```ts
{ ..., audience?: "users" | "devices" | "all" }   // default "users"
```

Only applies to `target: "broadcast"`. `"users"` is the pre-existing behaviour, so an admin client that
predates this field reaches exactly who it did before.

## What anonymous devices receive

Admin broadcasts only. Achievements, comment replies and review outcomes all route through
`notifications.send(db, user_id, ...)`, which filters on `user_id = <id>` — and in SQL `NULL` never
equals a value, so an anonymous row cannot receive a personal notification. `notifications.send()` now
refuses a falsy `user_id` outright rather than letting it degrade into `IS NULL`.

An anonymous broadcast writes one `notifications` row with `user_id = NULL`; the per-device trace is the
`push_delivery_tickets` rows keyed on token. Those `NULL`-user rows are invisible to
`GET /notifications` (which filters by user) and cannot be marked opened.
