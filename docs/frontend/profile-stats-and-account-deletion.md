# Profile Stats & Account Deletion — Frontend Integration

## Overview

Two changes, one bug fix and one new choice:

1. **"Likes received" on the profile was wrong.** It read 90 when the real number was 141. `UserPrivateRead` now carries the correct total so the app stops computing it.
2. **Deleting an account now asks whether to keep your games.** `DELETE /users/me` takes an optional flag.

Backend is on branch `fix/my-games-ordering` (`src/api/users.py`, `src/api/games.py`, `src/api/favourites.py`, `src/api/comments.py`, `src/db/tables.py`, `src/services/purge.py`). Pushed, **not merged, not deployed**. Tracked as #105.

## ⚠️ Needs a manual migration BEFORE deploy

`keep_games_on_delete` is a new column on an existing table, and it is an ordinary mapped column — every `SELECT` of a `User` includes it. If the deploy lands first, the column is missing and **every query touching `users` fails**: login, the auth dependency on every authenticated request, most of the API.

Run this against Railway Postgres first. The currently deployed code ignores a column it does not know about, so running it early is safe:

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS keep_games_on_delete BOOLEAN;
```

Script: `scripts/migrate_keep_games_on_delete.sql`. See `CLAUDE.md` § Production.

---

## 1. Profile stats

### The bug

`ProfileScreen.tsx` computed the stat client-side:

```ts
const totalUpvotes = myGames.reduce((sum, g) => sum + g.upvotes, 0);
```

`myGames` comes from `fetchMyGames()`, which calls `/games/mine?limit=20&offset=0`. The admin account has **26 games**, so six were never in the sum. Worse, `/games/mine` had no `ORDER BY`, so Postgres returned a different arbitrary 20 rows after any update — the number moved on its own without a single like being added or removed.

Confirmed in production: real total 141, app showed 90, and `Game.upvotes` matched the `user_favourites` rows exactly. Nothing was lost.

### What changed

`UserPrivateRead` gains two keys. Both are always present, both default to `0`:

```ts
games_uploaded: number;   // count of games this user contributed
likes_received: number;   // sum of upvotes across those games
```

They are derived server-side from `Game.upvotes`, not stored, so they can never drift from the number shown on a game card.

Returned by every endpoint that already returns `UserPrivateRead`:

- `GET /users/me`
- `PATCH /users/me`
- `POST /users/me/complete-profile`
- `POST /users/me/avatar`, `DELETE /users/me/avatar`

**No new request needed.** `ProfileScreen` already calls `refreshUser()`, which hits `/users/me`.

### The app change

`ProfileScreen.tsx` — replace the client-side sum:

```ts
// before
const totalUpvotes = myGames.reduce((sum, g) => sum + g.upvotes, 0);

// after — ?? keeps older backends working
const totalUpvotes = user?.likes_received ?? myGames.reduce((sum, g) => sum + g.upvotes, 0);
```

`GAMES UPLOADED` has the same problem — it renders `myGames.length`, which caps at 20:

```ts
const gamesUploaded = user?.games_uploaded ?? myGames.length;
```

Keep `?? ` until the minimum supported backend is guaranteed to send the fields, then drop the fallback.

**Do not raise `fetchMyGames()` to `limit=200` to fix this.** `/games/mine` eager-loads six collections per game (equipment, settings, contributor, aliases, photos, videos). Pulling 200 games to produce one integer is far more expensive than reading the field.

### Interim fix already live for shipped builds

Builds already in the stores keep summing one page of `/games/mine`, and no release reaches them for days. So the backend now orders `/games/mine` by `upvotes DESC` — the page carries as much of the real total as 20 rows can. If six or more of a user's games have zero likes, old builds land on the exact right number.

This does **not** change the order games appear in. The app re-sorts client-side (`sortedMyGames`, default "Newest"). It only changes which games a >20-game library pages in.

**Phase out:** once `LATEST_APP_VERSION` is a build reading `likes_received`, change the `order_by` in `get_my_games` back to `Game.created_at.desc()`. It is commented and pinned by a test in `tests/api/users/test_contribution_stats.py`.

---

## 2. Account deletion — "keep my games?"

### What the backend did before

`DELETE /users/me` starts a 30-day window; `run_purge` sweeps after it. For games it did two different things:

- **public** games → reassigned to a placeholder user ("Deleted User")
- **private** games → deleted outright

Published content was never at risk. But the author had no say, and the split had no recorded reason.

### What changed

```
DELETE /users/me?keep_games=true|false
```

Optional. The choice is stored on the user, so the sweep 30 days later honours it:

| `keep_games` | private games | public games |
|---|---|---|
| `true` | published with `status="pending"`, so they re-enter the review queue | reassigned to placeholder |
| `false` | deleted | reassigned to placeholder |
| omitted | deleted (unchanged) | reassigned to placeholder |

`true` **publishes** private games rather than just reassigning them. A private game owned by the placeholder would be unreachable — nobody signs in as the placeholder, and `GET /games/{id}` returns 403 on a non-public game to everyone but its contributor and admins. Reassigning alone would keep the row and lose the content.

Likes now survive too: purge reassigns `user_favourites` rows to the placeholder instead of deleting them, consistent with games, comments and approved aliases.

### The app change

Add the choice to the delete-account flow and pass it. **Until the app sends the flag, nothing changes** — omitted is treated as `false`, which is exactly today's behaviour.

Response body is unchanged:

```json
{ "message": "Account deactivated. You have 30 days to reactivate before your data is permanently deleted." }
```

### Copy this needs

The confirmation screen has to say what "keep my games" actually means, because it is not reversible after the 30-day window:

- games stay on the platform, attributed to a deleted account
- private games become public and go to review
- the choice cannot be withdrawn once the account is purged

Wording is not written yet. Relevant to the store/compliance items still outstanding on account deletion.

---

## Compatibility

Everything here is additive: two optional response fields and one optional query param. No `COMPATIBILITY.md` row needed, and `api-compat` passes without the `api-baseline-bump` label — verified, nothing removed or narrowed from the baseline.

Deploy order: **migration SQL → backend → app**.

## Open decisions

1. Should kept games keep the author's display name, or is placeholder attribution always right? Currently always placeholder.
2. A deleted account's republished private games all hit the review queue at once. Acceptable, or should they default to `rejected` for an admin to pull forward?
3. Should the choice be revocable during the 30-day window — does reactivating reset it? Currently the stored value just persists.
