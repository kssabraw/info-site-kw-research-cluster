-- M15 slice 3 — content scheduling schema (handoff.md §9.3 / §9.4).
--
-- Bulk "Schedule all" materializes one parent `content_schedules` row + N child
-- `scheduled_article_runs` (one per cluster). An in-process asyncio worker (slice 4) claims
-- due rows (FOR UPDATE SKIP LOCKED, cap 3) and writes the article. Pillars-first ordering is
-- decided by the planner, not the schema. RLS ON from day one (owner-all + session-owner via
-- a sessions join — mirrors article_outputs / keywords / site_architecture). Never using(true).

create table fanout.content_schedules (
  id           uuid primary key default gen_random_uuid(),
  session_id   uuid not null references fanout.sessions (id) on delete cascade,
  mode         text not null check (mode in ('all_at_once', 'drip', 'fixed')),
  per_day      int,                                  -- null unless drip; >=1 for drip
  start_date   date,
  time_of_day  time not null default '09:00',
  timezone     text not null default 'UTC',
  status       text not null default 'active'
               check (status in ('active', 'paused', 'complete', 'cancelled')),
  total_count  int not null,
  user_id      uuid not null,
  created_at   timestamptz not null default now()
);

create table fanout.scheduled_article_runs (
  id                   uuid primary key default gen_random_uuid(),
  content_schedule_id  uuid references fanout.content_schedules (id) on delete cascade,
  cluster_id           uuid not null references fanout.clusters (id) on delete cascade,
  session_id           uuid not null references fanout.sessions (id) on delete cascade,
  scheduled_at         timestamptz not null,
  status               text not null default 'queued'
                       check (status in ('queued', 'running', 'complete', 'failed', 'cancelled')),
  user_id              uuid not null,
  started_at           timestamptz,
  completed_at         timestamptz,
  error                text,
  created_at           timestamptz not null default now()
);

-- The worker's claim query scans queued rows by due time.
create index scheduled_article_runs_due_idx
  on fanout.scheduled_article_runs (status, scheduled_at) where status = 'queued';
create index scheduled_article_runs_schedule_idx
  on fanout.scheduled_article_runs (content_schedule_id);

-- Atomic backstop for the API's double-book guard: a cluster can have at most one *pending*
-- (queued/running) run at a time. Completed/failed/cancelled runs are unindexed, so a cluster
-- is freely re-schedulable once its prior run finished. The app-level pre-filter skips known
-- duplicates gracefully; this only fires on a true concurrent-schedule race (rejecting the
-- second insert) so two schedules can never both queue — and thus double-write — the same cluster.
create unique index scheduled_runs_one_pending_per_cluster
  on fanout.scheduled_article_runs (cluster_id) where status in ('queued', 'running');

-- Tie a generated article back to the run that produced it (null for ad-hoc generations).
alter table fanout.article_outputs
  add column scheduled_article_run_id uuid
    references fanout.scheduled_article_runs (id) on delete set null;

grant select, insert, update, delete on fanout.content_schedules to authenticated;
grant select, insert, update, delete on fanout.scheduled_article_runs to authenticated;
grant all on fanout.content_schedules to service_role;
grant all on fanout.scheduled_article_runs to service_role;

alter table fanout.content_schedules enable row level security;
alter table fanout.scheduled_article_runs enable row level security;

-- content_schedules — owner-all + session-owner (VA on own sessions, §9.9 #4).
create policy content_schedules_select on fanout.content_schedules
  for select to authenticated
  using (fanout.is_owner() or exists (
    select 1 from fanout.sessions s where s.id = content_schedules.session_id and s.user_id = auth.uid()));
create policy content_schedules_insert on fanout.content_schedules
  for insert to authenticated
  with check (fanout.is_owner() or exists (
    select 1 from fanout.sessions s where s.id = content_schedules.session_id and s.user_id = auth.uid()));
create policy content_schedules_update on fanout.content_schedules
  for update to authenticated
  using (fanout.is_owner() or exists (
    select 1 from fanout.sessions s where s.id = content_schedules.session_id and s.user_id = auth.uid()))
  with check (fanout.is_owner() or exists (
    select 1 from fanout.sessions s where s.id = content_schedules.session_id and s.user_id = auth.uid()));
create policy content_schedules_delete on fanout.content_schedules
  for delete to authenticated
  using (fanout.is_owner() or exists (
    select 1 from fanout.sessions s where s.id = content_schedules.session_id and s.user_id = auth.uid()));

-- scheduled_article_runs — same shape.
create policy scheduled_article_runs_select on fanout.scheduled_article_runs
  for select to authenticated
  using (fanout.is_owner() or exists (
    select 1 from fanout.sessions s where s.id = scheduled_article_runs.session_id and s.user_id = auth.uid()));
create policy scheduled_article_runs_insert on fanout.scheduled_article_runs
  for insert to authenticated
  with check (fanout.is_owner() or exists (
    select 1 from fanout.sessions s where s.id = scheduled_article_runs.session_id and s.user_id = auth.uid()));
create policy scheduled_article_runs_update on fanout.scheduled_article_runs
  for update to authenticated
  using (fanout.is_owner() or exists (
    select 1 from fanout.sessions s where s.id = scheduled_article_runs.session_id and s.user_id = auth.uid()))
  with check (fanout.is_owner() or exists (
    select 1 from fanout.sessions s where s.id = scheduled_article_runs.session_id and s.user_id = auth.uid()));
create policy scheduled_article_runs_delete on fanout.scheduled_article_runs
  for delete to authenticated
  using (fanout.is_owner() or exists (
    select 1 from fanout.sessions s where s.id = scheduled_article_runs.session_id and s.user_id = auth.uid()));

-- Worker claim (slice 4): atomically flip up to `cap` due rows queued -> running. PostgREST
-- can't express FOR UPDATE SKIP LOCKED, so the in-process loop calls this via rpc on the
-- service client. SKIP LOCKED means two ticks / replicas never grab the same row. Joins the
-- parent schedule so a paused/cancelled schedule's runs are never claimed (pause = toggle parent).
create or replace function fanout.claim_scheduled_runs(cap int)
returns setof fanout.scheduled_article_runs
language plpgsql
as $$
begin
  return query
  update fanout.scheduled_article_runs r
     set status = 'running', started_at = now()
   where r.id in (
     select r2.id
       from fanout.scheduled_article_runs r2
       join fanout.content_schedules cs on cs.id = r2.content_schedule_id
      where r2.status = 'queued' and r2.scheduled_at <= now() and cs.status = 'active'
      order by r2.scheduled_at
      limit greatest(cap, 0)
      for update of r2 skip locked
   )
  returning r.*;
end;
$$;

grant execute on function fanout.claim_scheduled_runs(int) to service_role;
