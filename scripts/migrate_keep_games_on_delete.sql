-- Adds the deletion-time "keep my games" choice to the existing `users` table on Railway
-- Postgres. create_all only creates missing TABLES, not missing columns on existing ones, so
-- this must be run manually against the production DB after deploying this change.
-- Safe to run multiple times — IF NOT EXISTS makes it idempotent.

ALTER TABLE users ADD COLUMN IF NOT EXISTS keep_games_on_delete BOOLEAN;

-- No backfill. NULL is meaningful here: it marks an account that was never asked the
-- question, and purge treats NULL exactly as the pre-existing behaviour (private games are
-- deleted with the account). Defaulting it either way would silently change what happens to
-- accounts already inside their 30-day window.
