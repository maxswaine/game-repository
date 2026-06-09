# Pre-Release Plan

All items target a single `feature/pre-release-hardening` branch where possible.
Items marked **[separate branch]** are architectural changes with higher breakage risk.

---

## Execution Order

| Phase | Items | Est. | Files touched |
|-------|-------|------|---------------|
| 1 — Mechanical fixes | TD#2, TD#12, TD#11, TD#8, TD#9 | ~1.5 hr | `user.py`, `users.py`, `game.py` |
| 2 — Cookie/auth | TD#6, TD#7 | ~1.5 hr | `auth.py` |
| 3 — Profile + user | TD#1, TD#4 | ~3 hr | `users.py`, `auth.py`, `tables.py` |
| 4 — Age filtering | new | ~4 hr | `games.py`, `search.py`, `utils/` |
| 5 — Content moderation | new | ~5 hr | `games.py`, `optimisation.py`, `services/`, `utils/age_filter.py` |
| 6 — OAuth CSRF | TD#3 | ~2 hr | `auth.py` |
| — | **[separate]** TD#5 JWT revocation | — | `security.py`, `auth.py` |
| — | **[separate]** TD#10 RBAC enforcement | — | multiple |

**Total in-branch estimate: ~1.5–2 days.**

---

## Phase 1 — Mechanical Fixes

Low risk. No logic changes. Do these first to clear noise.

### P1-a. `UserPublicRead.country_of_origin` nullable crash (TD#2)

`src/models/user_models/user.py:64`

Type is `str` (required) but DB column is `nullable`. OAuth users have `None` here.
`GET /games/` raises a Pydantic 500 for any game created by an OAuth user.

**Fix:** `country_of_origin: Optional[str] = None`

---

### P1-b. `DELETE /users/{user_id}` returns body with 204 (TD#12)

`src/api/users.py:199, 216`

HTTP 204 must not include a body. Some proxies/clients silently drop the response.

**Fix:** Change status code to `200`, or remove the return statement for a clean 204.

---

### P1-c. `avatar_url` accepts `javascript:` URLs (TD#11)

`src/models/user_models/user.py:93`

No format validation. Stored `javascript:alert(1)` is a stored XSS vector.

**Fix:** Add Pydantic `field_validator` that requires value to start with `https://`.

---

### P1-d. Raw DB exceptions leaked to client (TD#8)

`src/api/users.py:111–112`

```python
raise HTTPException(status_code=500, detail=f"Database error occurred: {str(e)}")
```

Exposes table names, column names, internal state.

**Fix:** `logger.error(e)` server-side, return `"An unexpected error occurred"` to client.

---

### P1-e. No text length limits on game fields (TD#9)

`src/models/game_models/game.py:13–29`, `src/models/optimisation_models/optimisation_models.py:8`

Unbounded text triggers unbounded OpenAI spend.

**Fix:** Add `max_length` to `description`, `objective`, `setup`, `rules` in `GameBase`.
Add `max_length` to `OptimisationRequest.original_text`. Suggested cap: 2000 chars per field.

---

## Phase 2 — Cookie / Auth

### P2-a. `ENV` vs `ENVIRONMENT` cookie inconsistency (TD#6) ← fixes OAuth bug

`src/api/auth.py:50, 113, 248, 249, 268, 287`

`secure` flag reads `ENV`, `samesite` reads `ENVIRONMENT`. In production with only one set:
- `SameSite=None` without `Secure` → rejected by all modern browsers
- `Secure=True` with `SameSite=lax` → breaks cross-origin cookie (OAuth flow dies)

This is the likely root cause of the Google OAuth issues.

**Fix:** Standardise on `ENV` everywhere in `auth.py`. One constant at module top:

```python
IS_PRODUCTION = os.getenv("ENV") == "production"
```

Use `IS_PRODUCTION` for both `secure` and `samesite` across all cookie calls.

---

### P2-b. No rate limiting on auth endpoints (TD#7)

`src/api/auth.py:22–54`

`POST /auth/token` and `POST /users/register` open to credential-stuffing.

**Fix:** Add `slowapi`. 5 requests/min per IP on login; 3/min on register.

```python
from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address)
```

Wire via FastAPI middleware in `src/main.py`.

---

## Phase 3 — Profile + User

### P3-a. `complete_profile()` is a no-op (TD#1)

`src/api/users.py:118–123`

Handler accepts `UserCompleteProfile` (DOB, country) but never reads or saves it. OAuth users
believe their profile was saved — it wasn't. Also blocks age filtering (no DOB in DB).

**Fix:** Apply `profile_data` fields to `current_user` and commit before returning.

---

### P3-b. OAuth username collision (TD#4)

`src/api/auth.py:219`, `src/db/tables.py:15`

Username derived from `email.split("@")[0]` with no uniqueness check or DB constraint.
`get_current_user()` uses `.first()` — collision resolves to wrong user.

**Fix:**
1. Add `unique=True` to `User.username` in `tables.py`.
2. In `google_callback`, wrap `db.commit()` in try/except `IntegrityError`. On collision,
   append incrementing suffix (`john_2`, `john_3`) until insert succeeds.

---

## Phase 4 — Age-Based Content Filtering

**Goal:** Users under 18 cannot see `18+` games (drinking games). Primary concern is card/dice
games — most are fine for all ages. The `18+` rating is the real target.

### Decisions (settled)

- **Anonymous users:** show up to `16+`. `18+` games hidden.
- **No DOB set:** treat as anonymous (show up to `16+`). Frontend forces profile completion
  post-OAuth, so this edge case is minimal.
- **Admin role:** bypass filter entirely.

### Age → allowed ratings mapping

| User age | Allowed ratings |
|----------|----------------|
| No DOB / anonymous | All Ages, 3+, 7+, 12+, 16+ |
| < 3 | All Ages |
| 3–6 | All Ages, 3+ |
| 7–11 | All Ages, 3+, 7+ |
| 12–15 | All Ages, 3+, 7+, 12+ |
| 16–17 | All Ages, 3+, 7+, 12+, 16+ |
| 18+ | all |

### Implementation

**New helper** `src/utils/age_filter.py`:

```python
from datetime import date
from src.models.enums.age_rating_enum import AgeRatingEnum

ALL_RATINGS = list(AgeRatingEnum)
RATINGS_TO_16 = [r for r in AgeRatingEnum if r != AgeRatingEnum.age_18]

def allowed_age_ratings(date_of_birth: date | None) -> list[AgeRatingEnum]:
    if date_of_birth is None:
        return RATINGS_TO_16
    age = (date.today() - date_of_birth).days // 365
    if age >= 18:
        return ALL_RATINGS
    if age >= 16:
        return RATINGS_TO_16
    if age >= 12:
        return [AgeRatingEnum.all_ages, AgeRatingEnum.age_3, AgeRatingEnum.age_7, AgeRatingEnum.age_12]
    if age >= 7:
        return [AgeRatingEnum.all_ages, AgeRatingEnum.age_3, AgeRatingEnum.age_7]
    if age >= 3:
        return [AgeRatingEnum.all_ages, AgeRatingEnum.age_3]
    return [AgeRatingEnum.all_ages]
```

**Apply filter in:**
- `GET /games/` — add `.filter(Game.age_rating.in_(allowed_age_ratings(current_user?.date_of_birth)))`
- `GET /games/mine` — same
- `GET /games/{game_id}` — return 403 if game rating not in allowed set
- `GET /games/search/` (`src/api/search.py`) — filter post-ranking before returning results

---

## Phase 5 — Content Moderation on Submission

**Goal:** Block slurs/hate speech for everyone. Block mature/explicit content from under-18
submitters. Preserve legitimate explicit content (drinking game terms, slang) for adult users.

### P5-a. Global hate-speech gate (all users)

**Decision: OpenAI Moderation API**

Free. No per-call cost. We already import `openai`. ~100ms per call.

Block **only** on `hate` and `hate/threatening`. All other categories pass through:

| Category | Block? | Reason |
|---|---|---|
| `hate` | Yes | Slurs, dehumanising language, antisemitic/racist content |
| `hate/threatening` | Yes | Hate combined with threats of violence |
| `harassment` | No | Too broad — banter in games triggers this |
| `sexual` | No | Would block legitimate 18+ games |
| `violence` | No | Would block legitimate survival/combat games |
| `illicit` | No | Covers drug refs — drinking games border this |

**New service** `src/services/moderation.py`:

```python
from openai import OpenAI

client = OpenAI()

def check_content(text: str) -> bool:
    """Returns True if content is safe to store."""
    response = client.moderations.create(
        model="omni-moderation-2024-09-26",
        input=text,
    )
    result = response.results[0]
    return not (result.categories.hate or result.categories.hate_threatening)
```

**Call sites** — `POST /games/`, `PATCH /games/{game_id}`, and `POST /optimise/`
(`src/api/games.py`, `src/api/optimisation.py`):
- Concatenate `name + description + rules` into single string, pass to `check_content`.
- On `False`: raise `HTTPException(422, "Content violates community guidelines")`.
- Do not leak which word triggered it.
- On API failure: log and allow through (same fail-open pattern as embedder).

---

### P5-b. Under-18 submission filter

**Goal:** Users under 18 cannot submit games containing sexual content or profanity, even if
that content would be allowed for an adult submitter.

The OpenAI Moderation API has no `profanity` category. Solution: keyword detection.
- Reuse `detect_adult_content()` from `src/utils/age_filter.py` (already catches sexual keywords).
- Add new `detect_profanity(text: str) -> bool` to `age_filter.py` with a curated keyword list.

**New functions in `src/utils/age_filter.py`:**

Leet-speak normalization runs first (`0→o`, `1→i`, `3→e`, `4→a`, `5→s`, `7→t`, `@→a`, `$→s`),
then word-boundary regex matching. This catches "sh1t" and "f4ck" while avoiding false positives
on innocent words that contain profane substrings (e.g. "cockroach", "assassin", "classic").

```python
import re

_LEET_MAP = str.maketrans({'0':'o','1':'i','3':'e','4':'a','5':'s','7':'t','@':'a','$':'s','!':'i'})

def _normalize(text: str) -> str:
    return text.lower().translate(_LEET_MAP)

_PROFANITY_PATTERNS = [
    r"\bfuck\w*\b",      # fuck, fucking, fucker
    r"\bshit\w*\b",      # shit, shitty, shitting
    r"\bcunt\w*\b",
    r"\bcock\b",         # NOT cockroach
    r"\bass\b",          # NOT assassin, classic
    r"\bbitch\w*\b",
    r"\bpussy\b",
    r"\basshole\b",
    r"\bwanker\b",
    r"\btwat\b",
    r"\bwhore\b",
    r"\bslut\w*\b",
    r"\bmotherfuck\w*\b",
]

_COMPILED_PROFANITY = [re.compile(p, re.IGNORECASE) for p in _PROFANITY_PATTERNS]

def detect_profanity(text: str) -> bool:
    normalized = _normalize(text)
    return any(p.search(normalized) for p in _COMPILED_PROFANITY)
```

**Call site** in `POST /games/` and `PATCH /games/{game_id}`, after resolving the current user:

```python
if not _user_is_adult(current_user):
    combined = f"{game.name} {game.description} {game.rules}"
    if detect_adult_content(...) or detect_profanity(combined):
        raise HTTPException(
            422,
            "You must be 18 or over to submit games containing mature or explicit content."
        )
```

No additional OpenAI call. Detection runs entirely in-process.

---

### P5-c. Moderation on optimise endpoint

Apply `check_content` to `original_text` in `POST /optimise/` before passing to GPT.
Prevents prompt injection attempts disguised as game text.
Call site: `src/api/optimisation.py`, before `get_optimiser(field_type).optimise(original_text)`.

---

## Phase 6 — OAuth CSRF

### P6-a. Missing `state` param in Google login (TD#3)

`src/api/auth.py:148–161`

No `state` parameter = no CSRF protection on OAuth callback. Attacker can craft a link
that completes OAuth for a victim's browser session.

**Fix:**
1. Add `starlette.middleware.sessions` (or `itsdangerous`) to `src/main.py`.
2. In `google_login`: generate `secrets.token_urlsafe(16)`, store in session, append as `&state=`.
3. In `google_callback`: read `state` param, compare to session value, raise 400 on mismatch.

---

## Post-Launch — Production Data Backfills

These are not code changes. Run against the Railway Postgres DB after deploying Phase 4 and 5.

### Backfill `has_adult_content` on existing games

The column was added with `DEFAULT FALSE`. All games created before Phase 4 deploy have
`has_adult_content = false` regardless of actual content. A backfill script must re-evaluate
each game using `detect_adult_content()` and update the column.

**Script:** `scripts/backfill_adult_content.py` — iterate all games, call `detect_adult_content`,
bulk update rows where result differs from stored value. Log count of updated rows.

### Backfill moderation on existing games

No existing games have been run through the OpenAI Moderation API. Post Phase 5 deploy, a
one-off script should check all public games for hate/hate-threatening content and either:
- Flag them for admin review (preferred), or
- Set `is_public = False` automatically (more aggressive)

**Decision needed:** Flag for review vs auto-hide. Either way, RBAC enforcement (separate branch)
is a prerequisite for an admin review queue to be useful.

**Script:** `scripts/backfill_moderation.py` — iterate public games, call `check_content`,
record flagged game IDs. Do not auto-delete.

---

## Separate Branch — Architectural Changes

These carry breakage risk and need their own PR + careful testing.

### JWT Revocation (TD#5)

`src/core/security.py:14` — 7-day tokens, no server-side invalidation, password changes don't
log out other sessions.

**Options:**
- Shorten to 1 day + use existing `/auth/refresh` endpoint.
- Add Redis `jti` denylist (more infrastructure).

**Decision needed before implementation.**

---

### RBAC Enforcement (TD#10)

`Role` enum stored on `User` but no endpoint checks it. `GameUpdateAdmin` model exists but
is unreachable. Admin review queue (for content moderation long-term) requires this.

**Fix:** `require_admin` FastAPI dependency, wire to admin-only routes.

---

## What Goes in One Branch

`feature/pre-release-hardening`:
- Phases 1–6 above (all security + new features)
- Excludes: JWT revocation, RBAC enforcement

Files changed: `auth.py`, `users.py`, `user.py`, `tables.py`, `game.py` (model),
`games.py` (API), `search.py`, `main.py` (slowapi middleware + session middleware),
new `src/utils/age_filter.py`, new `src/services/moderation.py`.
