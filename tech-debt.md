# Technical Debt

## Security Vulnerabilities

Identified via codebase security review on 2026-06-01. Ordered by priority.

---

### Fix Immediately

#### 1. `complete_profile()` is a no-op — silently discards user data

**File:** `src/api/users.py:118–123`

The handler accepts `UserCompleteProfile` (date_of_birth, country_of_origin) but never reads or saves `profile_data`. It
just returns the unchanged user. OAuth users redirected to `/complete-profile` after signup believe their profile has
been saved — it hasn't.

```python
def complete_profile(db, profile_data: UserCompleteProfile, current_user):
    return current_user  # profile_data is never used
```

**Fix:** Apply the fields from `profile_data` to `current_user` and commit.

---

#### 2. `UserPublicRead.country_of_origin` is non-optional but nullable in DB → crashes `GET /games/`

**Files:** `src/models/user_models/user.py:64`, `src/db/tables.py:22`

`UserPublicRead.country_of_origin` is typed as `str` (required). The DB column is `nullable=True`. OAuth users are
created with `country_of_origin=None` (see issue #1). `map_game_to_read()` embeds a `UserPublicRead` for every game's
contributor — so `GET /games/` raises a Pydantic validation error for any game created by an OAuth user, returning a
500.

**Fix:** Change `UserPublicRead.country_of_origin` to `Optional[str]`.

---

#### 3. OAuth CSRF — missing `state` parameter in Google login

**File:** `src/api/auth.py:148–161`

The Google OAuth authorization URL is constructed with no `state` parameter. Without it there is no CSRF protection on
the callback — an attacker can craft a link that completes an OAuth flow for a victim's session, potentially linking the
attacker's Google account to the victim's browser.

**Fix:** Generate a cryptographically random `state` value, store it in the session, append it to the Google auth URL,
and verify it in the callback before proceeding.

---

#### 4. OAuth username collision → wrong-user authentication

**Files:** `src/api/auth.py:219`, `src/db/tables.py:15`

When a Google OAuth user is created, their username is derived from their email prefix (`email.split("@")[0]`) with no
uniqueness check. The `username` column has no `unique=True` constraint in the ORM. Regular registration blocks
duplicate usernames, but OAuth creation does not. If a collision occurs, `get_current_user()` queries `.first()` on
`username`, which could resolve to the wrong user.

**Fix:** Add `unique=True` to the `username` column, and handle the collision in `google_callback` by appending a suffix
or prompting the user to choose a username.

---

### Fix Before Production Traffic

#### 5. No JWT revocation — stolen tokens remain valid for 7 days; password changes don't invalidate sessions

**File:** `src/core/security.py:14`

```python
TOKEN_EXPIRES_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))  # 7 days
```

Logout only deletes the cookie client-side. The JWT stays valid server-side for its full lifetime. Changing a password (
`src/api/users.py:190`) does not invalidate existing tokens — all previous sessions remain active.

**Fix:** Either shorten the token lifetime significantly and rely on the refresh endpoint, or implement a server-side
token denylist (e.g. a Redis set of invalidated `jti` claims).

---

#### 6. Inconsistent `ENV` vs `ENVIRONMENT` env var for cookie security settings

**File:** `src/api/auth.py:50–51, 113, 249`

Cookie `secure` and `samesite` flags are configured using two different env var names across three endpoints:

```python
secure = os.getenv("ENV") == "production"  # lines 50, 248
samesite = "none" if os.getenv("ENVIRONMENT") == "production"...  # lines 113, 249
```

If only one is set: `SameSite=None` without `Secure` (rejected by all modern browsers), or `Secure=True` with
`SameSite=lax` (breaks cross-origin auth). Either silently breaks production login.

**Fix:** Pick one env var name, use it consistently across all cookie configuration in `auth.py`.

---

#### 7. No rate limiting on auth endpoints

**File:** `src/api/auth.py:22–54`

`POST /auth/token` and `POST /users/register` have no rate limiting, IP throttling, or account lockout. Both are exposed
to credential-stuffing and brute-force attacks.

**Fix:** Add rate limiting middleware (e.g. `slowapi`) with a per-IP limit on login and registration.

---

### Fix Soon

#### 8. Registration error handler leaks raw exception messages to clients

**File:** `src/api/users.py:111–112`

```python
raise HTTPException(status_code=500, detail=f"Database error occurred: {str(e)}")
```

Unhandled DB exceptions (constraint violations, connection errors) have their raw message sent to the client,
potentially exposing table names, column names, or internal state.

**Fix:** Log the full exception server-side; return a generic message to the client.

---

#### 9. No text length limits on game fields or optimiser input — unbounded API spend

**Files:** `src/models/game_models/game.py:13–29`, `src/models/optimisation_models/optimisation_models.py:8`

`description`, `objective`, `setup`, and `rules` have no `max_length`. The optimiser's `original_text` has
`min_length=10` but no upper bound. An authenticated user can submit arbitrarily large text, triggering expensive OpenAI
embedding and GPT calls on demand.

**Fix:** Add `max_length` constraints to `GameBase` text fields and `OptimisationRequest.original_text`.

---

#### 10. `Role` enum stored on `User` but never enforced — RBAC is non-functional

**Files:** `src/models/enums/role_enum.py`, `src/models/game_models/game.py:60`

A `Role` enum (`user`/`admin`) is stored in the DB and a `GameUpdateAdmin` model exists with privileged fields (
`is_whats_that_game_certified`). No endpoint checks `current_user.role`. The admin role is stored but functionally
meaningless — there is no route to set `is_whats_that_game_certified` to `True`.

**Fix:** Add a `require_admin` dependency (alongside `get_current_active_user`) and wire it to any endpoints that should
be admin-only, including a future admin game update endpoint using `GameUpdateAdmin`.

---

### Cleanup

#### 11. `avatar_url` accepts any string including `javascript:` URLs

**File:** `src/models/user_models/user.py:93`

`UserUpdate.avatar_url` has no URL format validation. A stored `javascript:alert(1)` URL is a stored XSS vector if any
frontend renders it in an `<img src>` or `<a href>` without sanitisation.

**Fix:** Add a Pydantic `field_validator` that ensures `avatar_url` starts with `https://`.

---

#### 12. `DELETE /users/{user_id}` returns a body with HTTP 204

**File:** `src/api/users.py:199, 216`

HTTP 204 No Content must not include a response body. The endpoint returns a JSON message with a 204 status, which is
invalid and will be silently dropped by some clients and proxies.

**Fix:** Change `status_code` to `200`, or remove the `return` statement and let FastAPI return an empty 204.

---

## Summary Table

| #  | Issue                                | Severity | File                             |
|----|--------------------------------------|----------|----------------------------------|
| 1  | `complete_profile()` no-op           | Critical | `src/api/users.py`               |
| 2  | `UserPublicRead` nullable crash      | Critical | `src/models/user_models/user.py` |
| 3  | OAuth CSRF — no `state` param        | High     | `src/api/auth.py`                |
| 4  | OAuth username collision             | High     | `src/api/auth.py`                |
| 5  | No JWT revocation                    | High     | `src/core/security.py`           |
| 6  | `ENV` vs `ENVIRONMENT` inconsistency | High     | `src/api/auth.py`                |
| 7  | No rate limiting on auth             | High     | `src/api/auth.py`                |
| 8  | Exception messages leaked to client  | Medium   | `src/api/users.py`               |
| 9  | No text length limits                | Medium   | `src/models/`                    |
| 10 | RBAC not enforced                    | Medium   | multiple                         |
| 11 | `avatar_url` no validation           | Low      | `src/models/user_models/user.py` |
| 12 | 204 with response body               | Low      | `src/api/users.py`               |
