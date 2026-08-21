# API backward-compatibility check

CI (`.github/workflows/ci.yml`, job `api-compat`) runs [`oasdiff`](https://github.com/oasdiff/oasdiff)
against every PR: it generates the OpenAPI schema for the PR's code and diffs it against
`openapi-snapshot.json`, a schema snapshot committed to the repo. The build fails if the diff
contains a breaking change — a removed/renamed field, a field that changed type, a newly-required
field, a removed endpoint, etc.

This exists because of the deploy-order problem described in `CLAUDE.md` § Change Management: old
app builds keep calling this API until every user updates, and a build already submitted for App
Store/Play Store review can't be recalled. Tests prove the code behaves correctly *today* — they
don't stop someone from renaming a field next month that an old, unreachable app build still reads.
Schema diffing catches that at PR time, for every endpoint, without anyone having to remember to
write a contract test for it.

## What `openapi-snapshot.json` represents

Not "the last merged schema" — it's **the oldest schema shape the backend still promises to serve**.
It should almost never change. Adding fields/endpoints is always non-breaking, so normal feature
work never needs to touch it.

## When you'd update the snapshot

Only when deliberately dropping support for old app builds — i.e. paired with raising
`MIN_SUPPORTED_APP_VERSION` (see `docs/app-backend-version-signal.md`) once you've confirmed via the
`log_app_version` Railway logs that no live traffic depends on the old shape anymore. At that point,
regenerate it:

```bash
PYTHONPATH=. SECRET_KEY=x DATABASE_URL=sqlite:///./tmp.db python scripts/export_openapi.py openapi-snapshot.json
```

Commit the updated file in the same PR as the breaking change, with the reasoning (which app
versions are no longer supported, and why) in the PR description.

## Running the check locally

```bash
PYTHONPATH=. SECRET_KEY=x DATABASE_URL=sqlite:///./tmp.db python scripts/export_openapi.py openapi-current.json
oasdiff breaking openapi-snapshot.json openapi-current.json --fail-on ERR
```

(`oasdiff` binary: https://github.com/oasdiff/oasdiff/releases)
