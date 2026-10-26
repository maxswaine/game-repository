-- Per-device timezone, so notification automation can send at a sensible LOCAL hour.
-- create_all only creates missing TABLES, never adds columns to an existing one, so this must
-- be run manually against Railway Postgres.
--
-- ⚠️ RUN THIS *BEFORE* THE CODE DEPLOYS, not after.
--    `timezone` is an ordinary mapped column on PushToken, so every SELECT of push_tokens emits
--    it. Deploy first and every notification path (and push-token registration) breaks with
--    UndefinedColumn until this runs. The statement is backward compatible with the currently
--    deployed code (a nullable column it never reads), so running it early is safe; running it
--    late is an outage.
--
-- Safe to run multiple times.
-- Nothing is backfilled: NULL means "app build that predates the field" and the automation
-- treats those devices as UTC until the app next registers and reports its zone.
ALTER TABLE push_tokens ADD COLUMN IF NOT EXISTS timezone VARCHAR;
-- Last unrecognised name the app sent; powers GET /admin/notifications/timezones.
ALTER TABLE push_tokens ADD COLUMN IF NOT EXISTS timezone_error VARCHAR;

-- Verify (expect two rows, is_nullable = YES):
-- SELECT column_name, is_nullable FROM information_schema.columns
--  WHERE table_name = 'push_tokens' AND column_name IN ('timezone', 'timezone_error');
--
-- The new scheduled_notifications table needs no SQL: create_all builds it on first boot.
