-- Backfill achievements for users who earned them before the feature was deployed.
-- Safe to run multiple times — ON CONFLICT DO NOTHING skips already-granted rows.
-- Run each block individually or all at once in DBeaver.

-- first_like: has at least 1 entry in user_favourites
INSERT INTO user_achievements (user_id, achievement_type, achieved_at)
SELECT DISTINCT user_id, 'first_like', NOW()
FROM user_favourites
ON CONFLICT DO NOTHING;

-- first_submit: has submitted at least 1 game
INSERT INTO user_achievements (user_id, achievement_type, achieved_at)
SELECT DISTINCT contributor_id, 'first_submit', NOW()
FROM games
ON CONFLICT DO NOTHING;

-- five_uploads: has submitted 5 or more games
INSERT INTO user_achievements (user_id, achievement_type, achieved_at)
SELECT contributor_id, 'five_uploads', NOW()
FROM games
GROUP BY contributor_id
HAVING COUNT(*) >= 5
ON CONFLICT DO NOTHING;

-- ten_likes_on_upload: has at least one game with 10 or more upvotes
INSERT INTO user_achievements (user_id, achievement_type, achieved_at)
SELECT DISTINCT contributor_id, 'ten_likes_on_upload', NOW()
FROM games
WHERE upvotes >= 10
ON CONFLICT DO NOTHING;
