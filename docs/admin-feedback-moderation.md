# Admin feedback moderation — frontend implementation guide

Backend half is shipped on branch `feature/admin-feedback-moderation-actions`
(`src/api/feedback.py`, `src/models/feedback_models/feedback.py`). This covers what the app
(`whats-that-game-app`, `src/lib/api.ts` + `AdminScreen.tsx`) needs to pair with it. Mirrors the
existing report-resolution pattern (`resolveReport()` / `handleDismissReport` in `AdminScreen.tsx`)
— same shape, same endpoint, same UX, just for feedback instead of game reports.

## What changed

Feedback now has a small status lifecycle instead of just sitting there forever:

```
pending (default, new submissions)
  -> acknowledged   (seen, no further action needed)
  -> needs_work     (valid, worth revisiting later)
```

There's no user-facing "rejected" state — users never see how their feedback was actioned, so this
is purely an internal triage label for the team, not a response to the submitter.

**Behavior change:** `GET /admin/feedback` now only returns `status: "pending"` items. Once an
entry is acknowledged or marked needs-work, it drops out of the list entirely — that's intentional
(keeps the admin screen from growing forever), not a bug. If you ever need to see resolved feedback,
that's a direct DB query, not something the app surfaces.

## New endpoint

```
PATCH /admin/feedback/{feedback_id}
Body: { "action": "acknowledge" | "needs_work" }
Response: FeedbackAdminRead (200) — the updated row, including its new status
```

Errors: `422` if `action` isn't one of the two values, `404` if the feedback id doesn't exist,
`403` if not admin, `401` if unauthenticated.

## Frontend changes

1. **`src/lib/api.ts`** — add `resolveFeedback()` next to `resolveReport()`:

   ```ts
   export async function resolveFeedback(feedbackId: string, action: "acknowledge" | "needs_work") {
     return apiPatch(`/admin/feedback/${feedbackId}`, { action });
   }
   ```

2. **`AdminScreen.tsx`** — add Acknowledge / Needs Work buttons to the feedback card, same
   `actionsRow` pattern already used for game reports. On success, remove the item from local state
   (same as `handleDismissReport`) — the backend already excludes it from the next `GET
   /admin/feedback`, but removing it locally avoids a refetch round-trip.

   ```tsx
   const handleResolveFeedback = async (id: string, action: "acknowledge" | "needs_work") => {
     await resolveFeedback(id, action);
     setFeedbackItems(prev => prev.filter(f => f.id !== id));
   };
   ```

3. No new fields to add to the `FeedbackAdminRead` TS interface — `status` already exists on it
   (it just changes value now: `"pending" | "acknowledged" | "needs_work"` instead of `"open"`).

## Backend reference

- `src/models/feedback_models/feedback.py`: `FeedbackResolvePatch { action: str }`.
- `src/api/feedback.py`: `list_feedback` filters to `status == "pending"`; `resolve_feedback`
  (new `PATCH`) maps `action` -> `status` and returns the updated row.
- One-time prod migration required post-deploy: `scripts/migrate_feedback_status_to_pending.sql`
  (existing rows are `status='open'`, must move to `'pending'` or they silently vanish from the
  admin list under the new filter).
