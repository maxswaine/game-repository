# Force-Submitted Duplicates — Frontend Integration

## Overview

Submitting a game that looks like one already in the catalogue returns `409 potential_duplicate`. The app
then re-posts to `POST /games/?force=true`, which skips the check. That bypass was never recorded
anywhere — not in the DB, not in a log line — so a forced duplicate sitting in the review queue was
indistinguishable from one the duplicate check never flagged.

Two changes:

1. **`GameRead` gains `force_submitted: boolean`.** True when the contributor pushed past a duplicate
   warning. The admin review queue should show it.
2. **The duplicate check now logs what it decided.** No app-facing change, but it is why the numbers
   below are now knowable.

Backend is on branch `feature/record-force-submitted` (`src/db/tables.py`, `src/api/games.py`,
`src/models/game_models/game.py`, `src/services/embedder.py`, plus logging in `src/api/aliases.py`,
`src/api/search.py`, `src/services/{brain_dump,optimiser,storage}.py`). **Not merged, not deployed.**

## ⚠️ Needs a manual migration BEFORE MERGE

`force_submitted` is a new column on an existing table, and it is an ordinary mapped column — every
`SELECT` of a `Game` includes it. If the deploy lands first, the column is missing and **every query
touching `games` fails**: the home feed, search, favourites, `/games/mine`, game detail.

Railway deploys from `master` on merge, so **the merge button is the deploy** — the gate is merging the
PR, not a later step.

Run this against Railway Postgres **before the PR is merged**. Running it early is safe: the currently
deployed code ignores a column it does not know about.

```sql
ALTER TABLE games ADD COLUMN IF NOT EXISTS force_submitted BOOLEAN NOT NULL DEFAULT FALSE;
```

`FALSE` is the pre-existing behaviour, so backfilling every existing row with it changes nothing.

Script: `scripts/migrate_force_submitted.sql` — it also contains the backfill below. See `CLAUDE.md`
§ Production.

---

## 1. The new field

```ts
force_submitted: boolean;   // always present, defaults to false
```

Returned by every endpoint that already returns `GameRead` or `GameSearchResult`:

- `GET /games/`, `GET /games/mine`, `GET /games/{id}`, `GET /games/count`
- `POST /games/`, `PATCH /games/{id}`, `PATCH /games/{id}/visibility`
- `POST /games/{id}/verify`, `POST /games/{id}/unverify`, `PATCH /games/{id}/adult-content`
- `GET /favourites/`
- `POST /games/search/`
- `GET /admin/games/pending`, `PATCH /admin/games/{id}/review`

Additive, so no `COMPATIBILITY.md` row and no `MIN_SUPPORTED_APP_VERSION` bump. Old builds ignore the
key.

### Where it should surface

**Admin review queue only.** A reviewer opening a pending game needs to know the submitter was already
told it was a duplicate — that is the difference between "new write-up of a game we don't have" and
"second copy of a game we do".

Suggested: a badge on the pending-game row, e.g. `⚠ Duplicate warning overridden`, and a line in the
review detail view. The existing rejection reason codes already cover the outcome
(`GameRejectionReasonEnum`), so this is purely a signal to the reviewer, not a new reject path.

**Do not show it on public game cards.** It is a moderation signal, not a quality rating, and a game can
be force-submitted and still be a legitimate separate game.

## 2. Backfill — four games already in the queue

The Railway HTTP logs show a `409 Conflict` 1-3 seconds before each of these rows was created, followed
by a `POST /games/?force=true` `201 Created`:

| Game | Warnings shown | Forced at | Duplicate of |
|---|---|---|---|
| Go Fish | 1 | 2026-10-20 15:06 | Go Fish (approved 10-05) |
| Crazy Eights | 2 | 2026-10-20 15:24 | Crazy Eights 🤪 (approved 07-29) |
| GOPS | 3 | 2026-10-20 15:41 | — (judge flagged it; no name match in catalogue) |
| stress | 5 | 2026-10-20 15:56 | — (judge flagged it; closest is Speed) |

The migration script sets `force_submitted = TRUE` on these four by id. Everything else stays `FALSE`.

For context on the same queue: **Karekope** (pending, 10-20 13:16) is Kemps under a different name and
was **not** flagged — it scored ≈0.65 cosine, landed in the LLM judge's gray zone, and the judge did not
confirm it. So `force_submitted = false` means "no warning was shown", not "not a duplicate".

## 3. No change to the submit flow

The app already handles the 409 → `?force=true` round trip correctly; nothing to change there. The
response shape is unchanged:

```ts
// 409
{ detail: { code: "potential_duplicate", similar_games: Array<GameRead & { score: number }> } }
```

### Worth considering (not a backend ask)

On 2026-10-20, **five of seven** submissions that triggered a duplicate warning were pushed through
anyway, one after five separate warnings. That is a UX signal, not a user problem — the override is
currently as easy as the correct action.

Options, in rough order of effort:

1. Make the primary button on the duplicate sheet *"This is that game"* (opens the existing game),
   and demote "Submit anyway" to a text link.
2. Show the matched game's full card in the sheet, not just the name — several of these are genuine
   "I didn't recognise it from the title" cases.
3. If a warning is overridden, ask for one line of why, and put it in front of the reviewer.

(1) and (2) are frontend-only. (3) needs a backend field — say so and I'll add it alongside
`force_submitted` rather than as a second migration.

## 4. Testing

| Test | Pins |
|---|---|
| `tests/api/games/test_games_duplicate.py::test_force_submitted_records_the_bypass` | `force=true` → `true`; clean submit → `false` |
| `tests/services/test_embedder_text.py` | the duplicate check and the stored embedding build identical text |
| `tests/test_no_silent_handlers.py` | no `except` in `src/` swallows an error without logging it |
