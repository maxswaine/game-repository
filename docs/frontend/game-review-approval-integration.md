# Game Review / Approval Flow — Frontend Integration

## Overview

Games can now be **pending**, **approved**, or **rejected**. This backs two things:

1. **Submission gate** (behind a feature flag, currently OFF) — new submissions won't go public until an admin approves them.
2. **Report resolution** — admins can now act on the existing report queue (`POST /games/{id}/report`), rejecting a reported game or dismissing the report.

Every `GameRead` response (create, get, list, search, mine) now includes:

```json
{
  "...": "...existing fields...",
  "status": "pending",
  "rejection_reason_code": null,
  "rejection_reason": null
}
```

`status` is one of `"pending" | "approved" | "rejected"`.

---

## ⚠️ The submission gate is OFF right now

`GAME_REVIEW_GATE_ENABLED` is `false` in every environment today. That means:

- New games are created with `status: "approved"` immediately — **current behavior is unchanged**, nothing to build urgently.
- The gate will be flipped on **only after this doc's UI is live in a shipped app build** — there's no rush, but don't skip it, because once it flips:
  - New submissions will come back with `status: "pending"` and **will not appear in `GET /games/` or search** until approved.
  - A user submitting a game and then checking "my games" needs to see it's pending, or it'll look like data loss.

Coordinate the flip with backend once the "pending" UI below ships. Ping backend before merging your gate-off assumption anywhere permanent — this flag is scaffolding and gets deleted once the app is live on the App Store.

---

## What to build

### 1. Post-submission state (`POST /games/`)

No response shape change needed to handle — `status` is just present on the object you already get back. When gate is ON, show a toast/banner instead of "Game published!":

> "Thanks! Your game is in review and will be visible once approved."

### 2. "My Games" list (`GET /games/mine`)

This endpoint is **not** filtered by status — owners always see all their own games regardless of state. Use `status` to render a badge:

| `status` | Badge |
|---|---|
| `pending` | "Pending review" |
| `approved` | (no badge, or "Live") |
| `rejected` | "Not approved" — tap through to see why |

### 3. Rejected game detail

If `status === "rejected"`, show `rejection_reason` (free text, may be `null`) and optionally map `rejection_reason_code` to a friendlier label (table below). Let the owner edit and the game stays `rejected` until an admin re-reviews it — there's currently no auto-resubmit-to-pending on edit, so surface a "contact support" or similar path if you want re-review; flag to backend if you want edit-triggers-resubmit added.

### 4. Public surfaces (`GET /games/`, `GET /games/{id}`, search)

No change needed — the backend already filters to `status == "approved"` server-side. A non-owner hitting a pending/rejected game's detail page gets `403`, same as today's private-game behavior. Handle it the same way you already handle private-game 403s.

---

## Rejection reason codes

`GameRejectionReasonEnum` values (used in admin flows, and returned as `rejection_reason_code` on rejected games):

| Value | Suggested label |
|---|---|
| `Profanity` | Profanity |
| `Inappropriate Content` | Inappropriate content |
| `Adult Content Not Flagged` | Contains adult content (wasn't marked 18+) |
| `Duplicate Submission` | Duplicate of an existing game |
| `Low Quality / Unclear Rules` | Rules unclear or incomplete |
| `Spam` | Spam |
| `Other` | Other |

---

## Admin endpoints (only relevant if there's an admin surface in-app)

All require an admin JWT (`role: admin`), same auth as existing `/admin/*` routes (aliases, notifications). 403 for non-admins.

### List pending submissions
```
GET /admin/games/pending
```
→ `GameRead[]`, oldest first.

### Approve or reject a submission
```
PATCH /admin/games/{game_id}/review
Content-Type: application/json

{
  "status": "approved"
}
```
or
```
{
  "status": "rejected",
  "rejection_reason_code": "Duplicate Submission",
  "rejection_reason": "Same game as 'Cards Against Humanity Lite'"
}
```
→ `GameRead` with updated `status`/`rejection_reason_code`/`rejection_reason`.

`rejection_reason_code` is **required** when `status: "rejected"` — 422 if missing. `rejection_reason` (free text) is always optional.

### List open reports
```
GET /admin/games/reports
```
→
```json
[
  {
    "id": "report-id",
    "game_id": "game-id",
    "game_name": "Cards Against Humanity",
    "reporter_id": "user-id",
    "reason": "Spam",
    "status": "pending",
    "created_at": "2026-07-31T12:00:00Z"
  }
]
```

### Resolve a report
```
PATCH /admin/games/reports/{report_id}
Content-Type: application/json

{ "action": "dismiss" }
```
→ report marked `dismissed`, game untouched (stays exactly as it was, still public if it was public).

```json
{
  "action": "reject",
  "rejection_reason_code": "Inappropriate Content",
  "reason": "Optional extra detail"
}
```
→ report marked `actioned`, game set to `status: "rejected"` and immediately pulled from public listings/search. `rejection_reason_code` is required on `"reject"` — 422 if missing.

### List user feedback
```
GET /admin/feedback
```
→ `FeedbackAdminRead[]`, newest first:
```json
[
  {
    "id": "feedback-id",
    "user_id": "user-id",
    "type": "Bug Report",
    "message": "The upvote button double-counts sometimes",
    "status": "open",
    "created_at": "2026-07-31T12:00:00Z"
  }
]
```
Admin-only, same auth as the rest of `/admin/*` — 403 for non-admins, 401 unauthenticated. No filtering/pagination yet (flag to backend if the queue gets big enough to need it).

---

## Distinguishing "too long" from "policy violation" on 422s

Both `POST /games/` and `PATCH /games/{id}` can return 422 for two very different reasons — **don't show the same error copy for both**:

**1. Field length validation** (e.g. `description` over its `max_length`) — standard FastAPI/Pydantic shape, `detail` is an **array**:
```json
{
  "detail": [
    {
      "type": "string_too_long",
      "loc": ["body", "description"],
      "msg": "String should have at most 150 characters",
      "ctx": { "max_length": 150 }
    }
  ]
}
```
Use `loc[1]` to know which field, `ctx.max_length` for the limit — surface as an inline field error ("Description is too long — max 150 characters"), not a content-policy message.

**2. Content policy / age-gate blocks** — `detail` is an **object** with a stable `code`:
```json
{ "detail": { "code": "content_policy_violation", "message": "Content violates community guidelines." } }
```
```json
{ "detail": { "code": "age_restricted_content", "message": "You must be 18 or over to submit games containing mature or explicit content." } }
```

**How to branch on the client:** check `Array.isArray(body.detail)` first — if true, it's a validation error (map `loc`/`ctx` to the field); if false, read `body.detail.code` and switch on it (`content_policy_violation` | `age_restricted_content`) rather than string-matching `message`, since message text may change.

This distinction matters — a user hitting the 150-char description cap should never see "your content violates our guidelines," that's misleading and was reported as confusing via in-app feedback.

---

## Unrelated bonus fixes in this branch

`country_of_origin` is now optional everywhere on the user models (`UserBase`, `UserCreate`, `UserCompleteProfile`) — was previously required, blocking signup for anyone who declined to share it. No FE change needed unless you're currently hard-requiring the field client-side before submit; if so, you can relax that validation.

**`description` max length tightened to 150 characters** (`POST /games/` and `PATCH /games/{id}`). Was 2000. Add client-side validation/char-counter on the description field to match — a 151+ char submission now gets a 422. This does **not** affect reading existing games: older games with longer descriptions still return in full on `GET`, nothing there will suddenly break or truncate.

**`username` format now validated on signup (`POST /auth/register`), not just on update.** Allowed: letters, numbers, underscore, period. 3-30 characters. Anything else (spaces, `+`, `-`, apostrophes, etc.) now gets a 422 at signup — previously only blocked on `PATCH /users/me`. Add matching client-side validation on the signup username field so users get instant feedback instead of a submit-time 422. Note: OAuth signup (Google) auto-generates a username from the email prefix and bypasses this validator entirely, so OAuth-created usernames can still contain characters this rule would otherwise reject — not a FE concern, just don't assume all usernames in the DB conform.

**Comments now get a profanity check.** `POST /games/{game_id}/comments` runs the same profanity/moderation check games already use on `description`/`rules` etc. Applies to both `comment_type` values (`general` and `rule_variant` — i.e. rule-suggestion comments are covered too). A comment body that trips it gets a 422 with the same object-shape `detail` as the games endpoints (see "Distinguishing 'too long' from 'policy violation'" above): `{ "code": "content_policy_violation", "message": "Content violates community guidelines." }` — reuse the same client-side branch (`body.detail.code`), no separate parsing needed. No age exception here (unlike game submission, which only blocks profanity for under-18s) — blocked for everyone regardless of age.

---

## Error states summary

| Scenario | Status | Notes |
|---|---|---|
| Viewing own pending/rejected game | 200 | Always works via `/games/{id}` or `/games/mine` |
| Non-owner viewing pending/rejected game | 403 | Same handling as private-game 403 |
| Reject without `rejection_reason_code` | 422 | Both `/review` and `/reports/{id}` |
| Invalid `status` / `action` value | 422 | |
| Comment body contains profanity/flagged content | 422 | `POST /games/{id}/comments`, both comment types |
| Unknown `game_id` / `report_id` | 404 | |
| Non-admin hitting `/admin/games/*` or `/admin/feedback` | 403 | |
