-- M11 cost attribution (PRD §16.4).
-- Per-step cost breakdown for a session, populated by the background pipeline
-- jobs alongside the existing `actual_cost_usd` (which already exists from the
-- M1 initial migration). No RLS change: `sessions` already carries the §13
-- owner-all / owner-or-session-owner policies, and this is just another column.

alter table fanout.sessions
  add column if not exists cost_breakdown jsonb;
