-- Adds the deletion-time "keep my games" choice to the existing `users` table on Railway
-- Postgres. create_all only creates missing TABLES, not missing columns on existing ones.
--
-- RUN THIS BEFORE MERGING TO master, not after — Railway deploys on merge, so the merge
-- button is the deploy. keep_games_on_delete is an ordinary mapped column,
-- so every SELECT of a User includes it. Deploy first and the column is missing, which
-- fails every query that touches `users` — that is login, auth on every request, and most
-- of the API. Running it first is safe: the currently deployed code simply ignores a column
-- it does not know about.
--
-- Safe to run multiple times — IF NOT EXISTS makes it idempotent.

ALTER TABLE users ADD COLUMN IF NOT EXISTS keep_games_on_delete BOOLEAN NOT NULL DEFAULT false;

-- false is the pre-existing behaviour (private games are deleted with the account), so
-- backfilling every existing row with it — including accounts already inside their 30-day
-- window — changes nothing. There is no third "never asked" state to preserve.
