-- Adds the `force_submitted` flag to the existing `games` table on Railway Postgres.
-- create_all only creates missing TABLES, not missing columns on existing ones, so this must
-- be run manually against the production DB after deploying the feature/record-force-submitted code.
-- Safe to run multiple times — IF NOT EXISTS / explicit ids make each statement idempotent.

ALTER TABLE games ADD COLUMN IF NOT EXISTS force_submitted BOOLEAN NOT NULL DEFAULT FALSE;

-- Backfill for 2026-10-20: these four pending submissions were each preceded by a
-- "POST /games/ 409 Conflict" in the Railway HTTP logs 1-3 seconds before the row was
-- created, i.e. the contributor saw the duplicate warning and re-posted with force=true.
-- GOPS was warned three times and stress five times before going through.
UPDATE games SET force_submitted = TRUE WHERE id IN (
    '6722f4b1-cc64-4120-a351-1e1ae1fbdaa3',  -- Go Fish        (409 at 15:06:28, created 15:06:31)
    '8a683c62-42c5-4c33-ab4c-72c2e43ba459',  -- Crazy Eights   (409 at 15:24:38, created 15:24:40)
    '49cf2b3c-1d5f-4d55-902f-bffd9d96fd49',  -- GOPS           (409 at 15:41:12, created 15:41:13)
    '71105e89-4a26-41ef-a8e6-e6c82eb33a0c'   -- stress         (409 at 15:56:11, created 15:56:12)
);
