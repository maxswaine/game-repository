# Comment Replies — Frontend Integration

## Overview

Game comments become **single-level threads**: a reply attaches to a top-level comment and renders underneath it. Previously comments were flat, so a game owner answering a question had no way to attach the answer to it.

Backend half is built on branch `feature/comment-replies` (`src/api/comments.py`, `src/db/tables.py`, `src/services/notifications.py`). **Not pushed, not merged, not deployed.**

## ⚠️ Needs a manual migration before deploy

`parent_id` is a new column on an existing table. There's no Alembic layer here — `create_all` creates missing *tables* on startup but never missing *columns*. This must run against Railway Postgres **before** the deploy, or every query touching `game_comments` fails on boot, which is most of the API:

```sql
ALTER TABLE game_comments ADD COLUMN IF NOT EXISTS parent_id VARCHAR REFERENCES game_comments(id) ON DELETE CASCADE;
```

First column addition in this repo's history. See `CLAUDE.md` § Production.

## What changed

`CommentRead` gains two keys, both always present:

```ts
parent_id: string | null;   // null on a top-level comment
replies: CommentRead[];     // always an array; empty on a reply
```

### `GET /games/{game_id}/comments`

Now returns **top-level comments only**, each carrying its replies nested in `replies`, oldest first. Top-level sort unchanged: likes desc, then newest.

`limit` (default 20, max 200) now counts **top-level comments**, so one page can render well over 20 rows. `hasMore`-style checks against the returned length are still correct.

### `POST /games/{game_id}/comments`

Accepts an optional `parent_id`:

```json
{ "body": "You can also play this with 2 decks", "comment_type": "general", "parent_id": "<uuid>" }
```

| Case | Response |
|---|---|
| Valid reply | `201` with the created comment |
| `parent_id` not found, or belongs to another game | `404` |
| `parent_id` is itself a reply | `422`, `detail.code = "reply_depth_exceeded"` |
| Profanity / moderation | `422`, `detail.code = "content_policy_violation"` (unchanged) |

Nesting is capped at one level by design. The UI must resolve a reply-to-a-reply to its **parent** rather than relying on the API — passing the reply's own id returns 422.

### `DELETE /games/{game_id}/comments/{comment_id}`

Unchanged, but note deleting a parent **cascades its replies**. Worth a confirmation dialog naming the count; the current app deletes with no confirmation at all.

### Likes

`POST /games/{game_id}/comments/{comment_id}/like` works on replies with no change.

## Notifications

A reply notifies **the parent comment's author**, not the game contributor. Title is `"New reply"`. `notification_type` stays `new_comment` and `data` stays `{game_id}`, so existing tap handling works untouched.

There is **no `comment_id` in the payload**, so a tap lands on the game, not the comment. For a reply notification that's a weak landing — the user is told someone answered them, then has to go find it. Additive backend work if wanted; doesn't block this.

## Compatibility

Additive — no existing key changed shape or meaning. **No `COMPATIBILITY.md` row needed.** An old app build ignores both keys and shows top-level comments as before; replies didn't exist in any shipped build, so nothing regresses.

## Frontend work

Full UI spec — layout, inline composer, copy, edge cases — lives in the app repo at `docs/COMMENT_REPLIES_SPEC.md`, also published at https://claude.ai/artifact/UgqcFEUEiADiRk8GN4Bx21

The part worth flagging from this side: three handlers in `GameDetailScreen.tsx` treat `comments` as a flat array and **fail silently** against the nested shape — `handlePostComment` (`:1000-1005`) renders a reply as a root comment, `handleDeleteComment` (`:983-989`) leaves deleted replies on screen, and `handleLikeComment` (`:970-981`) never updates a liked reply even though the API call succeeds. None of them throw.

Trello: [#61](https://trello.com/c/PWtEdxPn)
