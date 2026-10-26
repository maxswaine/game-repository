# Notification Automation — Frontend Integration

## Overview

The backend now sends push notifications on a schedule: lifecycle pushes (day 2/3/7/14 after install) and an
admin-approved queue of drafted notifications. Sends are timed to each device's local hour (17:00 by default).

Everything is additive. **Nothing here is needed to keep working** — builds ≤ 1.1.2 behave exactly as before and
are sent to at 17:00 UTC. The app changes below make delivery land at the right local time and give admins an
approval screen.

Backend is on branch `feature/notification-automation`. **Not merged, not deployed.** Automation stays off
(`NOTIFICATION_AUTOMATION_ENABLED`) until the backend owner flips it.

## 1. Send the device timezone (app, all users)

`PushTokenCreate` gains `timezone?: string` — an IANA zone name, e.g. `"Europe/London"`.

```ts
const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
await api.post('/push-tokens/', { token, platform, device_id, timezone });
```

- Optional. Omitted = backend keeps whatever it has stored (an omitted zone never wipes a stored one).
- Unrecognised names are dropped silently, not rejected. Registration never fails because of this.
- No zone stored = treated as UTC.
- Send it on **every** register call, not just the first. The call already runs on app start / token refresh, so
  a user who travels or changes region self-corrects.
- No new endpoint, no new permission prompt.

## 2. Push-permission prompt copy (App Store)

Lifecycle and campaign pushes are promotional. Apple guideline 4.5.4 expects the in-app opt-in wording to say so.
Check the copy shown before the OS permission dialog says something like "tips, reminders and new-game updates",
not only "notifications about your games".

Opt-out is unchanged: turning notifications off (`DELETE /push-tokens/`) stops everything. There is no separate
marketing switch.

## 3. Admin approval screen (admin users only)

All endpoints need an admin JWT.

| Method | Path | Use |
|---|---|---|
| `GET` | `/admin/notifications/scheduled` | The calendar. No `status` = draft + approved, soonest first. Params: `status`, `batch_id`, `limit` (≤200) |
| `PATCH` | `/admin/notifications/scheduled/{id}` | Edit `title`, `body`, `send_at`, or set `status` to `draft` / `approved` / `cancelled` |
| `POST` | `/admin/notifications/scheduled/batches/{batch_id}/approve` | Approve every still-draft row in a batch |
| `POST` | `/admin/notifications/scheduled` | Create a batch of 1–50 drafts (admin or the Claude routine) |
| `GET` | `/admin/notifications/campaigns` | The fixed lifecycle campaigns (read only, copy lives in code) |
| `GET` | `/admin/notifications/timezones` | Timezone health: reported / not reported / invalid / UTC counts, top zones, `warning` string. Show it on the stats tab; a non-null `warning` means the app is sending bad or all-UTC zones |
| `GET` | `/admin/notifications/stats` | Sent / failed / opened per type. Param: `days` (default 30) |

Row shape (`ScheduledNotificationRead`): `id`, `batch_id`, `title`, `body`, `data`, `audience`, `send_at`,
`local_time`, `status`, `source`, `rationale`, `sent_zones`, `approved_at`, `sent_at`.

Screen needs:

1. **List grouped by `batch_id`**, soonest `send_at` first. Show title, body, `send_at`, `source`
   (`admin` / `claude`), and `rationale` (why Claude drafted it).
2. **Per-row cancel** (`PATCH status: "cancelled"`) and **edit** (title ≤ 65, body ≤ 178 chars).
3. **Approve batch** button → `POST .../batches/{id}/approve`. Cancel unwanted rows first.
4. **Editing an approved row resets it to `draft`** — the UI must show it needs re-approving.
5. **`local_time`**: true = `send_at` is a wall-clock time each device hits in its own zone. False = a UTC instant.
   Label it so an admin knows "17:00" does not mean 17:00 for everyone.
6. **Status badges**: `draft`, `approved`, `sent`, `cancelled`, `expired`. `expired` = approved but never sent
   in time; the backend drops late pushes rather than send at 4am.
7. **Stats tab** from `/stats`. A campaign sitting at 0 sent is the only visible sign of a broken one.

`send_at` is naive UTC in responses. Convert for display.

## Order of operations

1. Backend migration + deploy (backend owner).
2. Ship app build with `timezone` (§1, §2). Old builds keep working meanwhile.
3. Admin screen (§3) can ship any time after the backend deploy, independent of the app release.

No `COMPATIBILITY.md` row needed: no old build breaks and no new build requires a minimum backend, except that
§1 is ignored by a backend that predates this change (harmless).
