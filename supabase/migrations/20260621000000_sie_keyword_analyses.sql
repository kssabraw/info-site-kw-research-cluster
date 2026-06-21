-- M12 — SIE Term & Entity module (docs/sie-module-plan.md §5).
--
-- Per-keyword on-page term/entity analysis (SurferSEO/Clearscope-style), produced
-- lazily at write time and cached. The cache is keyed by keyword + location_code
-- and is CROSS-SESSION by design (the same keyword in two sessions reuses one
-- analysis); `session_id`/`cluster_id` are provenance only (nullable). Fresh if
-- `run_date` is within 7 days; `force_refresh` writes a new row; history is never
-- deleted. The pipeline cache lookup runs as the service role (bypasses RLS), so
-- cross-session reuse does not depend on the RLS policy below — that policy only
-- gates direct report reads via the API.
--
-- RLS ON from day one (this is exactly the cross-tenant-cache class that produced
-- the AR-Internal-Tools sie_cache "RLS forgotten" finding). Policy mirrors the
-- other fanout tables (owner-all + session-owner via a sessions join), per the
-- §9 sign-off — keyword_analyses holds SERP/competitor data, not user-sensitive
-- data, so consistency with keywords/site_architecture wins. Never `using (true)`.

create table fanout.keyword_analyses (
  id             uuid primary key default gen_random_uuid(),
  keyword        text not null,
  location_code  int  not null default 2840,
  language_code  text not null default 'en',
  outlier_mode   text not null default 'safe' check (outlier_mode in ('safe','aggressive')),
  output_json    jsonb not null,                                            -- the PRD Final Output Model
  cost_usd       numeric(10,4),
  session_id     uuid references fanout.sessions (id) on delete set null,   -- provenance only
  cluster_id     uuid references fanout.clusters (id) on delete set null,   -- provenance only
  run_date       timestamptz not null default now()
);

-- Cache lookup: latest fresh row for (keyword, location_code).
create index keyword_analyses_lookup_idx
  on fanout.keyword_analyses (keyword, location_code, run_date desc);

grant select, insert, update, delete on fanout.keyword_analyses to authenticated;
grant all on fanout.keyword_analyses to service_role;

alter table fanout.keyword_analyses enable row level security;

-- Owner sees all (so the cross-session cache works for the owner); else the
-- session's owner via session_id. A null/deleted-session row is owner-only.
create policy keyword_analyses_select on fanout.keyword_analyses
  for select to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = keyword_analyses.session_id and s.user_id = auth.uid()
    )
  );

create policy keyword_analyses_insert on fanout.keyword_analyses
  for insert to authenticated
  with check (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = keyword_analyses.session_id and s.user_id = auth.uid()
    )
  );

create policy keyword_analyses_update on fanout.keyword_analyses
  for update to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = keyword_analyses.session_id and s.user_id = auth.uid()
    )
  )
  with check (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = keyword_analyses.session_id and s.user_id = auth.uid()
    )
  );

create policy keyword_analyses_delete on fanout.keyword_analyses
  for delete to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = keyword_analyses.session_id and s.user_id = auth.uid()
    )
  );
