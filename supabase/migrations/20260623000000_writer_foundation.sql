-- M14 — Writer module foundation (docs/writer-module-plan.md §5).
--
-- Per-cluster generated article (Content Writer v1.7, degraded `1.7-no-context` +
-- no_citations path). Produced lazily at write time after Brief Gen (Input A) + SIE
-- (Input C) run as stage 1. One row per generation; a regenerate inserts a new row
-- and the latest-by-generated_at wins (history is never deleted), mirroring how
-- briefs / keyword_analyses keep history.
--
-- NOTE the re-sequence (writer-module-plan.md top note): `clusters.adapter_cache` is
-- NOT added — the original plan §5 cached the adapter's 4 LLM calls there, but those
-- calls dissolved when the full Brief Generator (M13) became the Writer's Input A. The
-- adapter is now a pure field-mapper over fanout.briefs + fanout.keyword_analyses, so
-- there is nothing to cache at the cluster level.
--
-- RLS ON from day one. Policy mirrors the other fanout tables (owner-all + session-owner
-- via a sessions join — same as keywords / site_architecture / csv_exports / briefs).
-- Never `using (true)`.

create table fanout.article_outputs (
  id                       uuid primary key default gen_random_uuid(),
  cluster_id               uuid not null references fanout.clusters (id) on delete cascade,
  session_id               uuid not null references fanout.sessions (id) on delete cascade,
  article_json             jsonb not null,                       -- full §6 Writer output object
  article_markdown         text  not null,
  article_html             text  not null,
  total_word_count         int,
  cost_usd                 numeric(10,4),
  schema_version_effective text  not null,                      -- e.g. "1.7-no-context"
  generated_at             timestamptz not null default now()
);

-- Latest-article lookup for a cluster.
create index article_outputs_lookup_idx
  on fanout.article_outputs (cluster_id, generated_at desc);

grant select, insert, update, delete on fanout.article_outputs to authenticated;
grant all on fanout.article_outputs to service_role;

alter table fanout.article_outputs enable row level security;

create policy article_outputs_select on fanout.article_outputs
  for select to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = article_outputs.session_id and s.user_id = auth.uid()
    )
  );

create policy article_outputs_insert on fanout.article_outputs
  for insert to authenticated
  with check (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = article_outputs.session_id and s.user_id = auth.uid()
    )
  );

create policy article_outputs_update on fanout.article_outputs
  for update to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = article_outputs.session_id and s.user_id = auth.uid()
    )
  )
  with check (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = article_outputs.session_id and s.user_id = auth.uid()
    )
  );

create policy article_outputs_delete on fanout.article_outputs
  for delete to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = article_outputs.session_id and s.user_id = auth.uid()
    )
  );
