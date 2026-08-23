-- feature/admin-feedback-moderation-actions changed the Feedback.status default from
-- 'open' to 'pending', and GET /admin/feedback now only returns status='pending' rows
-- (acknowledged/needs_work are resolved and intentionally hidden from the admin list --
-- query the DB directly if you need to see them). Run this once against the production DB
-- after deploying, or every existing 'open' feedback entry silently disappears from the
-- admin screen instead of showing up as pending.
-- Safe to run multiple times -- the WHERE clause makes it idempotent.

UPDATE feedback SET status = 'pending' WHERE status = 'open';
