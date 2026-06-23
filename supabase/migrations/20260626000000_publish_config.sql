-- Article publishing destinations (in-app is the source of truth; this stores per-session
-- push config). One jsonb so it's extensible across destinations, e.g.
--   {"github": {"repo": "owner/repo", "branch": "main", "content_path": "src/content/blog"},
--    "drive":  {"folder_id": "..."}}
-- No RLS change — `sessions` already carries the §13 policies; this is just another column.

alter table fanout.sessions add column publish_config jsonb not null default '{}'::jsonb;
