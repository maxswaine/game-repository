# Technical Debt

Updated 2026-06-30.

---

### Remaining Before Launch

#### 1. Forgot-password flow — JWT revocation not yet wired

**File:** `src/api/auth.py`

The forgot-password feature is not yet built. When it ships, the reset endpoint must increment `user.token_version` so that outstanding sessions are invalidated on password reset. Token lifetime is also still 7 days (`TOKEN_EXPIRES_MINUTES = 10080` in `src/core/security.py`) — revisit once refresh-token flow exists.

---

#### 2. `age_rating` DB column — drop after deploy

**File:** Railway Postgres console

`age_rating` column is now `nullable=True` in the ORM and unused by the app. `create_all` won't drop it automatically. After merging and deploying, drop it manually:

```sql
ALTER TABLE games DROP COLUMN age_rating;
```

---

### Accepted / Won't Fix Before Launch

- **Moderation fails open on OpenAI API error** — `check_content()` returns `True` on error, logs at `ERROR`. Acceptable for pre-launch; revisit if OpenAI reliability becomes a concern.

---

### Fixed This Sprint (2026-06-30)

- Text length limits added to all game fields and optimiser input
- `require_admin` dependency extracted and wired to alias approval endpoints
- `PATCH /me/password` now increments `token_version`
- `get_current_user_optional` now validates `ver` claim
- `age_rating` removed from all models, API params, and response schemas; replaced by `has_adult_content` boolean
