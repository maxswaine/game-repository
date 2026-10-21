-- Device-scoped push tokens: lets a signed-out device hold a push subscription.
-- create_all only creates missing TABLES, never adds or alters columns on an existing one,
-- so this must be run manually against Railway Postgres.
--
-- ⚠️ RUN THIS *BEFORE* THE CODE DEPLOYS, not after.
--    `device_id` is an ordinary mapped column on PushToken, so every SELECT of push_tokens
--    emits it. Deploy first and every notification path breaks with UndefinedColumn until
--    this runs — and anonymous registration would fail the NOT NULL on user_id as well.
--    Both statements are backward compatible with the currently-deployed code: a nullable
--    column it never writes, and a dropped constraint it never relied on. So running this
--    early is safe; running it late is an outage.
--
-- Safe to run multiple times — every statement is idempotent.

-- 1. A device that granted push permission before signing in has no user.
ALTER TABLE push_tokens ALTER COLUMN user_id DROP NOT NULL;

-- 2. Client-generated, stable per install. Keeps one row per device across Expo token
--    rotation and across sign-in, so audience='all' cannot reach the same device twice.
ALTER TABLE push_tokens ADD COLUMN IF NOT EXISTS device_id VARCHAR;
CREATE INDEX IF NOT EXISTS ix_push_tokens_device_id ON push_tokens (device_id);

-- 3. A broadcast to anonymous devices has no user to attribute its notification row to.
--    The per-device trace is the push_delivery_tickets rows keyed on token.
ALTER TABLE notifications ALTER COLUMN user_id DROP NOT NULL;

-- Verify (expect: user_id and device_id nullable on push_tokens, user_id nullable on
-- notifications; every existing row still has its user_id, since nothing is backfilled).
-- SELECT table_name, column_name, is_nullable FROM information_schema.columns
--  WHERE (table_name, column_name) IN (
--    ('push_tokens', 'user_id'), ('push_tokens', 'device_id'), ('notifications', 'user_id'))
--  ORDER BY table_name, column_name;
