# App → backend version signal — frontend implementation guide

Backend half is shipped on branch `fix/admin-report-feedback-username-and-recommended-verified`
(`src/main.py`, `src/utils/config.py`). This doc covers what the app (`whats-that-game-app`,
`src/lib/api.ts`) needs to do to pair with it. **Deploy the backend branch before shipping the app
build that adds the header** — the backend change is additive/backward-compatible, so it's safe to
ship first.

## 1. Send `X-App-Version` on every request

Add the header in the shared request layer (`src/lib/api.ts`) so it's attached to every call, not
per-endpoint. Use the app's own version string (e.g. from `app.json` / `expo-constants` /
`package.json` — whatever the app already uses to display its version in Settings).

```ts
// src/lib/api.ts
import Constants from "expo-constants";

const APP_VERSION = Constants.expoConfig?.version ?? "unknown";

// wherever the shared fetch/axios client is built:
headers: {
  ...existingHeaders,
  "X-App-Version": APP_VERSION,
}
```

Nothing on the backend requires this header — requests without it are logged as
`app_version=unknown` and still succeed. This is intentionally non-breaking so older, already-shipped
builds that don't send the header keep working.

## 2. Read `min_supported_app_version` from `GET /version`

The endpoint now returns:

```json
{
  "version": "0.1.0",
  "min_supported_app_version": ""
}
```

- `version` — current backend version (unchanged, existed before this ticket).
- `min_supported_app_version` — lowest app semver the backend still wants to serve without a
  "please update" nudge. **Empty string (`""`) means unset/not enforced — do not prompt.** This is
  the default until someone deliberately sets `MIN_SUPPORTED_APP_VERSION` in Railway env vars, so
  treat empty string as "no-op", not as "0.0.0".

Suggested flow: on app start (or periodically), call `GET /version`, compare
`min_supported_app_version` against the running app version with a semver comparator (e.g.
`semver.lt(APP_VERSION, data.min_supported_app_version)`), and if the app is behind, show a
non-blocking "update available" prompt (not a hard block — App Store/Play Store review lag means a
user might not be able to update immediately even if they want to).

```ts
import semver from "semver"; // or whatever semver lib the app already depends on

async function checkForRequiredUpdate() {
  const { version, min_supported_app_version } = await fetchVersion(); // existing GET /version call
  if (!min_supported_app_version) return; // unset — nothing to do
  if (semver.lt(APP_VERSION, min_supported_app_version)) {
    // show update prompt
  }
}
```

## 3. What NOT to do

- Don't hard-block requests client-side based on this — the backend doesn't reject old versions
  either. This is a visibility + soft-nudge mechanism, not an enforcement mechanism.
- Don't assume `min_supported_app_version` is always present/non-empty — handle the empty-string
  case explicitly (see above).

## Backend reference

- `src/main.py`: `log_app_version` middleware logs `app_version=<value> method=<m> path=<p>` for
  every request (visible in Railway logs — use this to see which live app versions are still
  calling old endpoints before deciding what `MIN_SUPPORTED_APP_VERSION` to set).
- `src/utils/config.py`: `MIN_SUPPORTED_APP_VERSION` env var, defaults to `""`.
- `GET /version` (`src/main.py`): returns `{version, min_supported_app_version}`.
