-- M13 — Brief Generator module (docs/brief-generator-module-plan.md §3 / §5).
--
-- Per-keyword content brief (Brief Generator v2.6, answer-engine-first), produced
-- lazily at write time and cached. Mirrors fanout.keyword_analyses EXACTLY: keyed by
-- keyword + location_code, CROSS-SESSION by design (the same keyword in two sessions
-- reuses one brief); session_id/cluster_id are provenance only (nullable). Fresh if
-- run_date is within 7 days; force_refresh writes a new row; history is never
-- deleted. The pipeline cache lookup runs as the service role (bypasses RLS), so
-- cross-session reuse does not depend on the RLS policy below — that policy only
-- gates direct brief reads via the API.
--
-- RLS ON from day one (same cross-tenant-cache class as keyword_analyses / the
-- AR-Internal-Tools sie_cache "RLS forgotten" finding). Policy mirrors the other
-- fanout tables (owner-all + session-owner via a sessions join). Never `using (true)`.

create table fanout.briefs (
  id             uuid primary key default gen_random_uuid(),
  keyword        text not null,
  location_code  int  not null default 2840,
  language_code  text not null default 'en',
  output_json    jsonb not null,                                            -- Brief Gen v2.6 output (Writer Input A)
  cost_usd       numeric(10,4),
  session_id     uuid references fanout.sessions (id) on delete set null,   -- provenance only
  cluster_id     uuid references fanout.clusters (id) on delete set null,   -- provenance only
  run_date       timestamptz not null default now()
);

-- Cache lookup: latest fresh row for (keyword, location_code).
create index briefs_lookup_idx
  on fanout.briefs (keyword, location_code, run_date desc);

grant select, insert, update, delete on fanout.briefs to authenticated;
grant all on fanout.briefs to service_role;

alter table fanout.briefs enable row level security;

create policy briefs_select on fanout.briefs
  for select to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = briefs.session_id and s.user_id = auth.uid()
    )
  );

create policy briefs_insert on fanout.briefs
  for insert to authenticated
  with check (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = briefs.session_id and s.user_id = auth.uid()
    )
  );

create policy briefs_update on fanout.briefs
  for update to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = briefs.session_id and s.user_id = auth.uid()
    )
  )
  with check (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = briefs.session_id and s.user_id = auth.uid()
    )
  );

create policy briefs_delete on fanout.briefs
  for delete to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = briefs.session_id and s.user_id = auth.uid()
    )
  );
