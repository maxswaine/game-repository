# Technical Debt

Updated 2026-07-16.

---

### Remaining Before Launch

#### 1. `age_rating` DB column — drop after deploy

**File:** Railway Postgres console

`age_rating` column is now `nullable=True` in the ORM and unused by the app. `create_all` won't drop it automatically. After merging and deploying, drop it manually:

```sql
ALTER TABLE games DROP COLUMN age_rating;
```

---

### Accepted / Won't Fix Before Launch

- **Moderation fails open on OpenAI API error** — `check_content()` returns `True` on error, logs at `ERROR`. Acceptable for pre-launch; revisit if OpenAI reliability becomes a concern.

---

### Fixed This Sprint (2026-07-16)

- `POST /auth/reset-password` double-submit no longer surfaces a false "invalid or expired" error — a replayed token carrying the already-applied password now returns the same 200 success instead of a version-mismatch 400. Previously a double-click/retry on the reset form would change the password in the DB but show the user an error, leaving them stuck trying their old password.
- `POST /auth/reset-password` now clears the `access_token` cookie on success (matching `/auth/logout`), so a stale browser session doesn't later surface a confusing "Could not validate credentials" 401.

### Fixed This Sprint (2026-06-30)

- Text length limits added to all game fields and optimiser input
- `require_admin` dependency extracted and wired to alias approval endpoints
- `PATCH /me/password` now increments `token_version`
- `get_current_user_optional` now validates `ver` claim
- `age_rating` removed from all models, API params, and response schemas; replaced by `has_adult_content` boolean
