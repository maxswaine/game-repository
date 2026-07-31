-- Adds the game review/approval columns to the existing `games` table on Railway Postgres.
-- create_all only creates missing TABLES, not missing columns on existing ones, so this must
-- be run manually against the production DB after deploying the feature/game-review-approval code.
-- Safe to run multiple times — IF NOT EXISTS / WHERE clauses make each statement idempotent.
-- Run each block individually or all at once in DBeaver.

ALTER TABLE games ADD COLUMN IF NOT EXISTS status VARCHAR NOT NULL DEFAULT 'pending';
ALTER TABLE games ADD COLUMN IF NOT EXISTS rejection_reason_code VARCHAR;
ALTER TABLE games ADD COLUMN IF NOT EXISTS rejection_reason VARCHAR;
ALTER TABLE games ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE games ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP;

-- Backfill: every game that existed before this feature shipped was already live under the
-- old rules (no approval gate) — mark them approved so they don't vanish from public listings.
UPDATE games SET status = 'approved' WHERE status = 'pending';
