-- M3 — Expansion pipeline. Adds the `keywords` table (PRD §13): raw keywords
-- surfaced by per-silo DataForSEO expansion + autocomplete, with source
-- attribution. M3 owns this table. Columns that depend on later milestones are
-- added by their owning migrations: relevance_score (M4); cluster_id,
-- serp_top_urls, is_primary_for_cluster, orchestrator_drop_reason (M5);
-- volume/cpc/kd (M8 metrics).

-- Status lifecycle (PRD §13). The full value set is created now so later
-- milestones don't need to ALTER the enum; M3 only ever writes 'active'.
create type fanout.keyword_status as enum (
  'active',
  'excluded',
  'covered',
  'filtered_relevance',
  'filtered_junk',
  'dropped_by_orchestrator'
);

create table fanout.keywords (
  id          uuid primary key default gen_random_uuid(),
  session_id  uuid not null references fanout.sessions (id) on delete cascade,
  topic_id    uuid not null references fanout.topics (id) on delete cascade,
  keyword     text not null,
  sources     text[] not null default '{}',
  status      fanout.keyword_status not null default 'active',
  created_at  timestamptz not null default now()
);
create index keywords_session_id_idx on fanout.keywords (session_id);
create index keywords_topic_id_idx on fanout.keywords (topic_id);

grant select, insert, update, delete on fanout.keywords to authenticated;
grant all on fanout.keywords to service_role;

alter table fanout.keywords enable row level security;

-- Visible/editable to the Owner (all) or the user who owns the parent session.
create policy keywords_select on fanout.keywords
  for select to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = keywords.session_id and s.user_id = auth.uid()
    )
  );

create policy keywords_insert on fanout.keywords
  for insert to authenticated
  with check (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = keywords.session_id and s.user_id = auth.uid()
    )
  );

create policy keywords_update on fanout.keywords
  for update to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = keywords.session_id and s.user_id = auth.uid()
    )
  )
  with check (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = keywords.session_id and s.user_id = auth.uid()
    )
  );

create policy keywords_delete on fanout.keywords
  for delete to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = keywords.session_id and s.user_id = auth.uid()
    )
  );
