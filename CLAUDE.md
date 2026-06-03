# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the dev server
uvicorn src.main:app --reload

# Run all tests
pytest

# Run a single test file
pytest tests/api/games/test_games_post.py -v

# Run a single test by name
pytest tests/api/games/test_games_post.py::TestClassName::test_method_name -v

# Start the local Postgres database via Docker
docker-compose up -d
```

Environment variables are loaded from `.env` via `python-dotenv`. Required vars: `DATABASE_URL`, `SECRET_KEY`,
`OPENAI_API_KEY`. Google OAuth also requires `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, and
`FRONTEND_URL`.

## Production (Railway)

Backend is hosted on **Railway**. Production database is a Railway-managed Postgres instance.

**No Alembic migrations** — `Base.metadata.create_all(bind=engine)` in `src/main.py` runs on every startup and
auto-creates any tables defined in `src/db/tables.py` that don't yet exist in the DB.

**When adding a new table:** deploying to Railway is sufficient — `create_all` will create the missing table on startup.
No manual SQL needed. Verify by checking Railway logs for any SQLAlchemy errors on boot.

**`user_achievements` table** (added in `feature/achievements`): will be auto-created on first deploy of that
branch/merge to master.

## Architecture

This is a **FastAPI** REST API for "What's That Game" — a platform to store and discover games.

### Layers

- **`src/api/`** — route handlers. Each module creates one or more `APIRouter` instances and is registered in
  `src/main.py`.
- **`src/services/`** — business logic that calls external services (OpenAI).
- **`src/db/`** — SQLAlchemy engine/session (`database.py`) and ORM table definitions (`tables.py`).
- **`src/models/`** — Pydantic request/response models, grouped by domain (`game_models/`, `user_models/`, etc.) plus
  `enums/`.
- **`src/core/`** — JWT/bcrypt security (`security.py`) and shared HTTP exceptions (`exceptions.py`).
- **`src/utils/`** — `config.py` (env var loading), `prompts.py` (OpenAI prompt templates for the optimiser).

### Routers and endpoints

All routers are registered in `src/main.py`:

| Prefix          | Module                           | Auth     |
|-----------------|----------------------------------|----------|
| `/users`        | `src/api/users.py`               | mixed    |
| `/games`        | `src/api/games.py` (two routers) | mixed    |
| `/auth`         | `src/api/auth.py`                | open     |
| `/favourites`   | `src/api/favourites.py`          | required |
| `/metadata`     | `src/api/metadata.py`            | open     |
| `/optimise`     | `src/api/optimisation.py`        | required |
| `/games/search` | `src/api/search.py`              | open     |

**Games endpoints:**

- `GET /games/` — list public games. Query params for filtering: `name`, `game_type`, `age_rating`, `min_players`,
  `max_players`, `duration`, `difficulty`, `setting`, `equipment`. Pagination: `limit` (max 100, default 20) and
  `offset`.
- `GET /games/mine` — authenticated user's own games (paginated).
- `GET /games/{game_id}` — public; private games return 403 unless you are the contributor.
- `POST /games/` — create a game (auth required). Triggers embedding on creation.
- `PATCH /games/{game_id}` — update game fields (owner only). Re-embeds on save.
- `PATCH /games/{game_id}/visibility` — toggle `is_public` (owner only).
- `POST /games/{game_id}/upvote` — toggle upvote. Uses `UserFavourites` to track per-user state; also
  increments/decrements `Game.upvotes`.
- `POST /games/{game_id}/report` — stub endpoint, always returns `"Report received"`.
- `DELETE /games/{game_id}` — delete game (owner only).

**Favourites endpoints** (`/favourites`, all require auth):

- `GET /favourites/` — paginated list of the current user's favourited games (returns full `GameRead`).
- `POST /favourites/{game_id}` — add a game to favourites (400 if already favourited).
- `DELETE /favourites/{game_id}` — remove a game from favourites.

**Metadata endpoints** (open):

- `GET /metadata/countries` — sorted list of `{code, name}` pairs (via `pycountry`).
- `GET /metadata/metadata` — all valid enum values: `game_types`, `age_ratings`, `game_settings`, `game_equipment`,
  `durations`, `difficulty`.

**Search endpoint:**

- `POST /games/search/` — body: `{query: str, limit: int}`. Embeds the query, applies hard filters (e.g. "no equipment"
  phrases), then ranks public games by cosine similarity. Returns `GameSearchResult` (GameRead + `score`). Only games
  with a stored embedding are searched.

**Other endpoints:**

- `GET /version` — returns app version from `VERSION` file.

### Key design decisions

**Games router split**: `src/api/games.py` exports two routers — `protected_router` (requires auth) and
`public_router` (open). Both are mounted at `/games` in `main.py`. This keeps auth concerns out of individual handler
decorators.

**Upvotes share the `UserFavourites` table**: `POST /games/{game_id}/upvote` adds/removes a `UserFavourites` row to
track whether the current user has upvoted, and also updates the `Game.upvotes` counter. The separate `/favourites`
endpoints do the same. This means an upvote and a favourite are the same underlying record — adding a favourite also
counts as an upvote.

**Embeddings**: When a game is created or updated, `src/services/embedder.py` calls OpenAI's `text-embedding-3-small` to
generate a vector, stored as a JSON string in `Game.embedding`. Failures are silently swallowed — the game saves without
an embedding and can be backfilled with `scripts/embed_games.py`. Semantic search (`/games/search`) embeds the query and
applies hard-filters before cosine similarity ranking.

**AI optimiser**: `POST /optimise/` accepts a request body with `field_type` (validated against `AIAgentEnum`:
`description`, `objective`, `setup`, `rules`) and `original_text`. `src/services/optimiser.py` dispatches to a
`TextOptimiser` that uses a per-field system prompt from `src/utils/prompts.py` and calls OpenAI `gpt-4.1-nano`. Returns
`OptimisationResponse` with `success`, `data` (`OptimisationResult`), and optional `error_message`.

**Auth**: JWT tokens are issued at `/auth/token` (password) and via Google OAuth at `/auth/oauth/google`. Tokens are set
as `httponly` cookies and also returned in the response body for bearer-token clients (mobile).
`get_current_active_user` / `get_current_user_optional` in `src/api/users.py` are the shared auth dependencies.

**CORS**: Origins are configured via the `CORS_ORIGINS` env var (comma-separated, default `http://localhost:3000`).

### Database tables

Defined in `src/db/tables.py`:

- **`User`** — `id` (UUID), `firstname`, `lastname`, `username`, `email`, `hashed_password`, `date_of_birth`,
  `country_of_origin` (2-char ISO), `role` (`Role` enum: `user`/`admin`), `is_active`, `oauth_provider`, `oauth_id`,
  `avatar_url`, `created_at`, `last_updated`.
- **`Game`** — `id` (UUID), `name`, `description`, `age_rating`, `game_type`, `min_players`, `max_players`, `duration`,
  `difficulty`, `objective`, `setup`, `rules`, `image_url`, `is_public`, `upvotes`, `embedding` (JSON string),
  `is_whats_that_game_verified`, `contributor_id` (FK → users), `created_at`.
- **`UserFavourites`** — composite PK `(game_id, user_id)`. Used for both favourites and upvote tracking.
- **`GameEquipment`** — one row per equipment item per game (`game_id`, `equipment_name`). Cascade-deleted with the
  game. Default equipment is `"No Equipment"`.
- **`GameSetting`** — one row per setting per game (`game_id`, `setting_name`). Cascade-deleted with the game.

### Enums

Located in `src/models/enums/`:

`GameTypeEnum`, `AgeRatingEnum`, `GameDifficultyEnum`, `GameSettingEnum`, `GameEquipmentEnum`, `DurationEnum`, `Role`,
`Vote` (vote type), `AIAgentEnum` (valid optimiser field types).

### Test setup

Tests use SQLite (`test.db`) instead of Postgres. `tests/conftest.py` creates the schema once per session and wraps each
test in a transaction that rolls back, keeping tests isolated. The `client_with_auth`, `client_no_auth`, and
`client_as_second_user` fixtures override FastAPI's `get_db` and `get_current_active_user` dependencies. Shared
game/user payload builders live in `tests/utils.py`. `tests/api/games/helper.py` provides imperative helpers (
`create_public_game()`, `create_private_game()`, `create_user()`, `get_user_token()`, `upvote_game()`) for use inside
tests.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:

- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use
  `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a
  scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough
  context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
