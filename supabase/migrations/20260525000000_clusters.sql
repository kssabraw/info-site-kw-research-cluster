-- M5 — Article planning orchestrator + cross-topic dedup (PRD §7.10, §13).
--
-- Adds the canonical user-facing unit (`clusters` = one planned article) and the
-- orchestrator-flagged `coverage_gaps`, plus the per-keyword columns the
-- orchestrator writes. M5 owns these. The per-topic orchestrator decisions go to
-- the existing `sessions.orchestrator_log` jsonb (created in M1); no change there.
--
-- `clusters.primary_keyword_id` -> `keywords` and `keywords.cluster_id` ->
-- `clusters` form a deliberate cycle: a cluster names its primary keyword, and a
-- keyword names its owning cluster. Both sides are nullable so the staged write
-- in storage can insert clusters first, link keywords, then backfill the primary.

-- Article intent (PRD §13 clusters.intent). Inferred by the orchestrator from
-- SERP composition (§7.10.1.4), not a separate classification pass.
create type fanout.cluster_intent as enum (
  'informational',
  'commercial',
  'transactional',
  'comparison',
  'navigational'
);

-- Coverage-gap lifecycle (PRD §13). The user accepts (-> placeholder cluster) or
-- dismisses a flagged gap; acceptance/dismissal UI is M7, but the column set is
-- owned here so M7 doesn't ALTER it.
create type fanout.coverage_gap_status as enum (
  'pending',
  'accepted',
  'dismissed'
);

-- ---------------------------------------------------------------------------
-- clusters — one row per planned article (PRD §13).
-- ---------------------------------------------------------------------------
create table fanout.clusters (
  id                            uuid primary key default gen_random_uuid(),
  topic_id                      uuid not null references fanout.topics (id) on delete cascade,
  name                          text not null,
  -- nullable to break the FK cycle during the staged insert; set once the
  -- primary keyword row is known.
  primary_keyword_id            uuid references fanout.keywords (id) on delete set null,
  intent                        fanout.cluster_intent not null default 'informational',
  suggested_h2s                 text[] not null default '{}',
  peer_article_links            uuid[] not null default '{}',
  -- the Louvain grouping id this article derived from (e.g. "<topic_id>:g0");
  -- a free-text debug handle, not an FK. Null for gap placeholders.
  source_statistical_grouping_id text,
  orchestrator_notes            text,
  is_user_edited                boolean not null default false,
  is_gap_placeholder            boolean not null default false,
  centroid_embedding            public.vector(1536),
  created_at                    timestamptz not null default now()
);
create index clusters_topic_id_idx on fanout.clusters (topic_id);

grant select, insert, update, delete on fanout.clusters to authenticated;
grant all on fanout.clusters to service_role;

alter table fanout.clusters enable row level security;

-- Visible/editable to the Owner (all) or the user who owns the cluster's
-- grandparent session (via topic -> session). Mirrors the keywords policy.
create policy clusters_select on fanout.clusters
  for select to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.topics t
      join fanout.sessions s on s.id = t.session_id
      where t.id = clusters.topic_id and s.user_id = auth.uid()
    )
  );

create policy clusters_insert on fanout.clusters
  for insert to authenticated
  with check (
    fanout.is_owner()
    or exists (
      select 1 from fanout.topics t
      join fanout.sessions s on s.id = t.session_id
      where t.id = clusters.topic_id and s.user_id = auth.uid()
    )
  );

create policy clusters_update on fanout.clusters
  for update to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.topics t
      join fanout.sessions s on s.id = t.session_id
      where t.id = clusters.topic_id and s.user_id = auth.uid()
    )
  )
  with check (
    fanout.is_owner()
    or exists (
      select 1 from fanout.topics t
      join fanout.sessions s on s.id = t.session_id
      where t.id = clusters.topic_id and s.user_id = auth.uid()
    )
  );

create policy clusters_delete on fanout.clusters
  for delete to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.topics t
      join fanout.sessions s on s.id = t.session_id
      where t.id = clusters.topic_id and s.user_id = auth.uid()
    )
  );

-- ---------------------------------------------------------------------------
-- coverage_gaps — orchestrator-flagged missing articles (PRD §13).
-- ---------------------------------------------------------------------------
create table fanout.coverage_gaps (
  id                  uuid primary key default gen_random_uuid(),
  topic_id            uuid not null references fanout.topics (id) on delete cascade,
  suggested_title     text not null,
  target_keyword      text,
  rationale           text,
  status              fanout.coverage_gap_status not null default 'pending',
  accepted_cluster_id uuid references fanout.clusters (id) on delete set null,
  created_at          timestamptz not null default now()
);
create index coverage_gaps_topic_id_idx on fanout.coverage_gaps (topic_id);

grant select, insert, update, delete on fanout.coverage_gaps to authenticated;
grant all on fanout.coverage_gaps to service_role;

alter table fanout.coverage_gaps enable row level security;

create policy coverage_gaps_select on fanout.coverage_gaps
  for select to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.topics t
      join fanout.sessions s on s.id = t.session_id
      where t.id = coverage_gaps.topic_id and s.user_id = auth.uid()
    )
  );

create policy coverage_gaps_insert on fanout.coverage_gaps
  for insert to authenticated
  with check (
    fanout.is_owner()
    or exists (
      select 1 from fanout.topics t
      join fanout.sessions s on s.id = t.session_id
      where t.id = coverage_gaps.topic_id and s.user_id = auth.uid()
    )
  );

create policy coverage_gaps_update on fanout.coverage_gaps
  for update to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.topics t
      join fanout.sessions s on s.id = t.session_id
      where t.id = coverage_gaps.topic_id and s.user_id = auth.uid()
    )
  )
  with check (
    fanout.is_owner()
    or exists (
      select 1 from fanout.topics t
      join fanout.sessions s on s.id = t.session_id
      where t.id = coverage_gaps.topic_id and s.user_id = auth.uid()
    )
  );

create policy coverage_gaps_delete on fanout.coverage_gaps
  for delete to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.topics t
      join fanout.sessions s on s.id = t.session_id
      where t.id = coverage_gaps.topic_id and s.user_id = auth.uid()
    )
  );

-- ---------------------------------------------------------------------------
-- keywords — orchestrator-written columns (PRD §13).
-- ---------------------------------------------------------------------------
alter table fanout.keywords
  add column cluster_id           uuid references fanout.clusters (id) on delete set null,
  add column serp_top_urls        text[],
  add column is_primary_for_cluster boolean not null default false,
  add column orchestrator_drop_reason text;
create index keywords_cluster_id_idx on fanout.keywords (cluster_id);

-- ---------------------------------------------------------------------------
-- session_status — move the pipeline terminus downstream of /expand (handoff §4).
-- /expand now ends at 'awaiting_article_planning'; /plan-articles sets 'complete'.
-- ---------------------------------------------------------------------------
alter type fanout.session_status add value if not exists 'awaiting_article_planning';
