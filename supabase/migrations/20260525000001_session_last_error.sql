-- Async pipeline execution: surface why a background run failed.
-- /expand, /plan-articles, and /regate now run in a background worker and return
-- immediately; the frontend polls session status. When a background job fails it
-- sets status='error' with no open request to carry the detail, so we persist a
-- short reason here for the UI to show.

alter table fanout.sessions
  add column last_error text;
