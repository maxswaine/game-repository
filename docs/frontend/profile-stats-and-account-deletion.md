# Profile Stats & Account Deletion — Frontend Integration

## Overview

Two changes, one bug fix and one new choice:

1. **"Likes received" on the profile was wrong.** It read 90 when the real number was 141. `UserPrivateRead` now carries the correct total so the app stops computing it.
2. **Deleting an account now asks whether to keep your games.** `DELETE /users/me` takes an optional flag.

Backend is on branch `fix/my-games-ordering` (`src/api/users.py`, `src/api/games.py`, `src/api/favourites.py`, `src/api/comments.py`, `src/db/tables.py`, `src/services/purge.py`). Pushed, **not merged, not deployed**. Tracked as #105.

## ⚠️ Needs a manual migration BEFORE MERGE

`keep_games_on_delete` is a new column on an existing table, and it is an ordinary mapped column — every `SELECT` of a `User` includes it. If the deploy lands first, the column is missing and **every query touching `users` fails**: login, the auth dependency on every authenticated request, most of the API.

Railway deploys from `master` on merge, so **the merge button is the deploy** — the gate is merging the PR, not a later deploy step.

Run this against Railway Postgres **before the PR is merged** — Railway deploys on merge, so the merge button is the deploy. Running it early is safe: the currently deployed code ignores a column it does not know about.

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS keep_games_on_delete BOOLEAN NOT NULL DEFAULT false;
```

`false` is the pre-existing behaviour, so backfilling existing rows with it — including accounts already inside their 30-day window — changes nothing.

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

**Population:** every game with `contributor_id = you` — private, pending and rejected included. That is deliberately the same filter `/games/mine` uses, so the card's count and the list's length describe the same set. Pinned by `test_stats_count_the_same_games_as_my_games`.

They are computed per request from `Game.upvotes`, not stored on the user, so they can never disagree with the number on a game card. (`Game.upvotes` is itself a stored counter, so this is consistency with the card, not with a live count of `user_favourites` rows.)

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

### There is no server-side fix for already-shipped builds

Builds already in the stores keep summing one page of `/games/mine`, so they keep showing the understated number until users update. That is accepted deliberately.

Ordering `/games/mine` by `upvotes DESC` was tried, to make the page carry as much of the real total as 20 rows can. It was reverted: for a library over 20 games it pushes a **freshly-created, unliked game off page 1**, and since the app never pages past the first 20, the user's new game disappears from My Games. A missing game is worse than a low stat.

`/games/mine` is ordered newest-first, matching the list's label. Pinned by `test_my_games_pages_newest_first`.

The stat is only correct once the app reads `likes_received`.

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
| `false` (default) | deleted | reassigned to placeholder |
| omitted | same as `false` — unchanged behaviour | reassigned to placeholder |

The column is `NOT NULL DEFAULT false`. There is no "never asked" state: it would behave identically to `false`, so it isn't tracked.

**Reactivating clears the choice.** An answer belongs to the deletion it was given for, so cancelling within the 30-day window resets it to `false`. A later deletion request starts from the default rather than silently inheriting a `true` from months earlier.

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

Deploy order: **migration SQL → merge (deploys backend) → app release**.

## Open decisions

1. Should kept games keep the author's display name, or is placeholder attribution always right? Currently always placeholder.
2. A deleted account's republished private games all hit the review queue at once. Acceptable, or should they default to `rejected` for an admin to pull forward?
3. ~~Should the choice be revocable during the 30-day window?~~ **Decided:** reactivating resets it to `false`.
