-- Prod invariant checks. Every query below should return ZERO rows (or a zero count).
-- Anything non-zero is a real inconsistency worth explaining. Read-only — safe to paste
-- into the Railway Postgres console as a whole.
--
-- Usage: run it, then read the `check` column of any row that came back.

-- 1. Upvote counter drift. Game.upvotes is denormalised and shares UserFavourites with the
--    favourites endpoints, so the counter and the rows can disagree.
SELECT 'upvote counter drift' AS check, g.id, g.name, g.upvotes AS counter, COUNT(uf.user_id) AS actual
FROM games g
LEFT JOIN user_favourites uf ON uf.game_id = g.id
GROUP BY g.id, g.name, g.upvotes
HAVING g.upvotes <> COUNT(uf.user_id)
ORDER BY ABS(g.upvotes - COUNT(uf.user_id)) DESC
LIMIT 50;

-- 2. Negative counters — should be structurally impossible.
SELECT 'negative upvotes' AS check, id, name, upvotes
FROM games WHERE upvotes < 0;

-- 3. Public games that never passed review.
SELECT 'public but not approved' AS check, id, name, status, created_at
FROM games WHERE is_public = true AND status <> 'approved'
ORDER BY created_at DESC LIMIT 50;

-- 4. Approved games that are invisible to semantic search (embedding silently failed).
--    Backfill with scripts/embed_games.py.
SELECT 'missing embedding' AS check,
       COUNT(*) FILTER (WHERE embedding IS NULL) AS without_embedding,
       COUNT(*) AS total_public_approved,
       ROUND(100.0 * COUNT(*) FILTER (WHERE embedding IS NULL) / NULLIF(COUNT(*), 0), 1) AS pct_missing
FROM games WHERE is_public = true AND status = 'approved';

-- 5. Push receipt checker health. Tickets should not sit unchecked forever; a large old
--    `pending` + NULL checked_at population means the receipts job is not running in prod.
SELECT 'unchecked push tickets' AS check,
       status,
       COUNT(*) AS tickets,
       MIN(created_at) AS oldest,
       COUNT(*) FILTER (WHERE checked_at IS NULL) AS never_checked
FROM push_delivery_tickets
GROUP BY status ORDER BY tickets DESC;

-- 6. Notification send-failure rate by type. `no_token` is expected (user never opted in);
--    a meaningful `failed` share is not.
SELECT 'notification status mix' AS check, type, status, COUNT(*) AS rows
FROM notifications
GROUP BY type, status ORDER BY type, rows DESC;

-- 7. Push token freshness. Only meaningful AFTER the updated_at fix ships — before that,
--    updated_at is frozen at first registration.
SELECT 'push token freshness' AS check,
       platform,
       COUNT(*) AS tokens,
       COUNT(*) FILTER (WHERE updated_at > now() - interval '7 days')  AS seen_7d,
       COUNT(*) FILTER (WHERE updated_at < now() - interval '30 days') AS stale_30d
FROM push_tokens GROUP BY platform;

-- 7b. Anonymous device rows — tokens registered before sign-in, and how many were claimed.
--     These are legitimately user_id IS NULL, so check 8 excludes them from "orphan".
SELECT 'anonymous push tokens' AS check,
       platform,
       COUNT(*) FILTER (WHERE user_id IS NULL) AS anonymous,
       COUNT(*) FILTER (WHERE user_id IS NULL AND device_id IS NULL) AS anonymous_no_device_id,
       COUNT(*) FILTER (WHERE user_id IS NOT NULL) AS claimed
FROM push_tokens GROUP BY platform;

-- 8. Orphaned rows — FK cascades that did not fire, or rows pointing at deleted parents.
--    NOTE: notifications and push_tokens both allow a NULL user_id by design (anonymous
--    device broadcasts), so a NULL user_id is only an orphan when it is also non-NULL. The
--    `user_id IS NOT NULL` guards below keep those from inflating the count.
SELECT 'orphan equipment' AS check, COUNT(*) FROM game_equipment ge
  LEFT JOIN games g ON g.id = ge.game_id WHERE g.id IS NULL
UNION ALL
SELECT 'orphan settings', COUNT(*) FROM game_settings gs
  LEFT JOIN games g ON g.id = gs.game_id WHERE g.id IS NULL
UNION ALL
SELECT 'orphan favourites (game gone)', COUNT(*) FROM user_favourites uf
  LEFT JOIN games g ON g.id = uf.game_id WHERE g.id IS NULL
UNION ALL
SELECT 'orphan favourites (user gone)', COUNT(*) FROM user_favourites uf
  LEFT JOIN users u ON u.id = uf.user_id WHERE u.id IS NULL
UNION ALL
SELECT 'orphan notifications', COUNT(*) FROM notifications n
  LEFT JOIN users u ON u.id = n.user_id WHERE n.user_id IS NOT NULL AND u.id IS NULL
UNION ALL
SELECT 'orphan push tokens', COUNT(*) FROM push_tokens pt
  LEFT JOIN users u ON u.id = pt.user_id WHERE pt.user_id IS NOT NULL AND u.id IS NULL;

-- 9. Games with no contributor, or pointing at a user that no longer exists.
SELECT 'game without live contributor' AS check, g.id, g.name, g.contributor_id
FROM games g LEFT JOIN users u ON u.id = g.contributor_id
WHERE g.contributor_id IS NULL OR u.id IS NULL
LIMIT 50;

-- 10. Review bookkeeping: rejected without a reason, or reviewed with no reviewer.
SELECT 'bad review bookkeeping' AS check, id, name, status, rejection_reason_code, reviewed_by, reviewed_at
FROM games
WHERE (status = 'rejected' AND rejection_reason_code IS NULL)
   OR (reviewed_at IS NOT NULL AND reviewed_by IS NULL)
LIMIT 50;

-- 11. Duplicate accounts by email/username, case-insensitively — auth looks these up with
--     lower(), so two rows differing only in case are a login ambiguity.
SELECT 'dup email (case-insensitive)' AS check, lower(email) AS value, COUNT(*)
FROM users GROUP BY lower(email) HAVING COUNT(*) > 1
UNION ALL
SELECT 'dup username (case-insensitive)', lower(username), COUNT(*)
FROM users GROUP BY lower(username) HAVING COUNT(*) > 1;

-- 12. Active users with neither a password nor an OAuth identity — cannot log in at all.
--     Excludes the soft-delete placeholder user (config.DELETED_USER_ID), which has neither
--     by design.
SELECT 'user with no login method' AS check, id, email, oauth_provider, created_at
FROM users
WHERE is_active = true AND hashed_password IS NULL AND oauth_id IS NULL
  AND id <> '00000000-0000-0000-0000-000000000001'
LIMIT 50;
