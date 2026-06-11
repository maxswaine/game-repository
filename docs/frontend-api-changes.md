# Frontend API Changes — game-content-quality branch

This document covers every API behaviour change that the frontend must handle for the
game-content-quality feature. Each section lists the endpoint, what changed, and what the
frontend needs to do.

Use `graphify query "<endpoint or feature>"` in the frontend repo to locate which services,
hooks, or components make each call.

---

## 1. `GameRead` — new `aliases` field

**Endpoints affected (all endpoints that return `GameRead`):**
- `GET /games/`
- `GET /games/{game_id}`
- `GET /games/mine`
- `POST /games/`
- `PATCH /games/{game_id}`
- `POST /games/{game_id}/upvote`

**Change:** Every `GameRead` response now includes:

```json
"aliases": ["BS", "Bullshit"]
```

Empty array `[]` when the game has no approved aliases. Non-breaking additive change.

**Frontend action required:**
- On the game detail page, if `aliases.length > 0`, render an "Also known as: X, Y" line beneath the game name.
- Optionally render alias tags on game list cards.

---

## 2. `POST /games/` — new 409 duplicate warning

**Change:** Before saving, the server embeds the submission and compares it against existing
games. If any game scores ≥ 0.88 cosine similarity, the request is rejected with:

```json
HTTP 409 Conflict
{
  "detail": {
    "code": "potential_duplicate",
    "similar_games": [
      { "id": "...", "name": "BS", "score": 0.94, "description": "...", ... }
    ]
  }
}
```

The user can override by resubmitting with `?force=true`.

**Frontend action required:**
- Intercept 409 on game creation. Do **not** clear the form or redirect.
- Show a modal/inline warning: "This game might already exist" with the similar games listed (name + score, each linking to its detail page).
- Provide a "Submit anyway" button that resends the identical request to `POST /games/?force=true`.
- Show a loading state while the second request is in flight.

---

## 3. New endpoints — Game Aliases

### `POST /games/{game_id}/aliases`

**Auth:** Required.

**Request body:**
```json
{"alias": "BS"}
```

**Responses:**

| Status | Meaning |
|---|---|
| `201` | Suggestion saved with `status: "pending"`. Body: `AliasRead`. |
| `401` | Not authenticated |
| `404` | Game not found |

**Frontend action required:**
- Add a "Suggest a name" link/button on the game detail page (authenticated users only).
- On 201: show "Thanks — your suggestion is under review."

---

### `GET /games/{game_id}/aliases`

**Auth:** Open.

Returns list of approved aliases for a game:

```json
[{"id": "...", "game_id": "...", "alias": "BS", "suggested_by": "...", "status": "approved", "created_at": "..."}]
```

**Frontend action required:** Not required separately — approved aliases are already included in
`GameRead.aliases`. Use this endpoint only if you need the full alias metadata (e.g. to show
who suggested an alias).

---

## 4. New endpoints — Admin Alias Review

These endpoints are admin-only (`role === "admin"`). Non-admins receive `403`.

### `GET /admin/aliases`

Returns all pending alias suggestions across all games.

```json
[{"id": "...", "game_id": "...", "alias": "BS", "suggested_by": "...", "status": "pending", "created_at": "..."}]
```

### `PATCH /admin/aliases/{alias_id}`

**Request body:**
```json
{"status": "approved"}
```
or
```json
{"status": "rejected"}
```

**Responses:**

| Status | Meaning |
|---|---|
| `200` | Updated. Body: `AliasRead`. On approval, game is re-embedded server-side. |
| `403` | Not admin |
| `404` | Alias not found |
| `422` | Invalid status value |

**Frontend action required:**
- Build a protected `/admin/aliases` page (guard with `role === "admin"`).
- Show a table of pending suggestions with game name, suggested alias, submitter, and date.
- Approve / Reject buttons per row — call `PATCH /admin/aliases/{id}`.
- On 200: remove row from pending list, show toast.

---

## 5. New endpoints — Game Comments

### `GET /games/{game_id}/comments`

**Auth:** Open (optional — `liked_by_me` is populated for authenticated callers).

Query params: `limit` (default 20, max 100), `offset` (default 0).

Returns list sorted by likes descending:

```json
[
  {
    "id": "...",
    "game_id": "...",
    "user": {"username": "alice", "country_of_origin": "GB"},
    "body": "We play this slightly differently...",
    "comment_type": "rule_variant",
    "likes": 3,
    "liked_by_me": true,
    "created_at": "..."
  }
]
```

`comment_type` is either `"general"` or `"rule_variant"`.

**Frontend action required:**
- Render a comments section on game detail pages.
- Show `comment_type === "rule_variant"` with a "Rule variant" badge.
- Show like count + like button (filled if `liked_by_me`, unfilled otherwise).
- Show delete button only when `comment.user.username === currentUser.username`.
- `liked_by_me` is always `false` for unauthenticated callers — show empty like button.
- Implement "Load more" pagination if response returns exactly `limit` items.

---

### `POST /games/{game_id}/comments`

**Auth:** Required.

**Request body:**
```json
{"body": "We skip the setup step entirely", "comment_type": "general"}
```

`comment_type` defaults to `"general"`. Use `"rule_variant"` when the user is explicitly describing a rule difference.

**Responses:**

| Status | Meaning |
|---|---|
| `201` | Comment created. Body: `CommentRead`. |
| `401` | Not authenticated |
| `404` | Game not found |
| `422` | Body exceeds 1000 characters |

**Frontend action required:**
- Add a comment form below the comments list (authenticated users only).
- Include `comment_type` selector (e.g. radio: "General comment" / "Rule variant").
- Enforce 1000-char limit client-side with a live counter.
- On 401: show "Sign in to comment."

---

### `DELETE /games/{game_id}/comments/{comment_id}`

**Auth:** Required. Own comment only (admins can delete any).

**Responses:**

| Status | Meaning |
|---|---|
| `204` | Deleted |
| `403` | Not your comment |
| `404` | Comment not found |

**Frontend action required:**
- On 204: remove comment from list without page reload.
- On 403: show "You can only delete your own comments."

---

### `POST /games/{game_id}/comments/{comment_id}/like`

**Auth:** Required. Toggles like on/off.

**Response:** `200` with updated `CommentRead` (new `likes` count, updated `liked_by_me`).

**Frontend action required:**
- Update like count and button state in place from the response — no page reload.
- On 401: prompt login.

---

## Summary table

| Endpoint | Method | What changed | Frontend handles |
|---|---|---|---|
| `/games/` | GET | `aliases: string[]` on every game | display "Also known as" |
| `/games/{id}` | GET | `aliases: string[]` on game | display "Also known as" |
| `/games/` | POST | 409 if similar game found | duplicate warning modal + `?force=true` resubmit |
| `/games/{id}/aliases` | POST | New — suggest alias | suggest form on game detail |
| `/games/{id}/aliases` | GET | New — list approved aliases | optional metadata use |
| `/admin/aliases` | GET | New — list pending (admin) | admin review page |
| `/admin/aliases/{id}` | PATCH | New — approve/reject (admin) | approve/reject buttons |
| `/games/{id}/comments` | GET | New — list comments | comments section on game detail |
| `/games/{id}/comments` | POST | New — create comment | comment form |
| `/games/{id}/comments/{id}` | DELETE | New — delete comment | delete button |
| `/games/{id}/comments/{id}/like` | POST | New — toggle like | like button |
