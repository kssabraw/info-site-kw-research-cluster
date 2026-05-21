-- M2 — Silo discovery. Adds the `topics` table (PRD §13): one row per silo
-- proposed/accepted during silo discovery. M2 owns this table; later milestones
-- add keywords/clusters/etc. in their own migrations.

-- Relationship taxonomy (PRD §5.1). peer_entity is included because a user may
-- assert one for a custom silo (PRD Q17), even though the LLM never proposes it.
create type fanout.relationship_type as enum (
  'property_or_mechanism',
  'use_case',
  'effect_or_outcome',
  'practical_commercial',
  'research_or_trial',
  'broader_class',
  'peer_entity'
);

create type fanout.topic_source as enum (
  'llm_proposed',
  'user_added',
  'llm_proposed_then_user_edited'
);

create table fanout.topics (
  id                          uuid primary key default gen_random_uuid(),
  session_id                  uuid not null references fanout.sessions (id) on delete cascade,
  name                        text not null,
  rationale                   text,
  relationship_type           fanout.relationship_type not null default 'property_or_mechanism',
  supporting_evidence         text,
  source                      fanout.topic_source not null default 'llm_proposed',
  is_broader_class            boolean not null default false,
  embedding                   public.vector(1536),
  is_gated_for_competitor_mining boolean not null default false,
  created_at                  timestamptz not null default now()
);
create index topics_session_id_idx on fanout.topics (session_id);

grant select, insert, update, delete on fanout.topics to authenticated;
grant all on fanout.topics to service_role;

alter table fanout.topics enable row level security;

-- A topic is visible/editable to the Owner (all) or to the user who owns the
-- parent session. Scope is derived from the parent session's user_id.
create policy topics_select on fanout.topics
  for select to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = topics.session_id and s.user_id = auth.uid()
    )
  );

create policy topics_insert on fanout.topics
  for insert to authenticated
  with check (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = topics.session_id and s.user_id = auth.uid()
    )
  );

create policy topics_update on fanout.topics
  for update to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = topics.session_id and s.user_id = auth.uid()
    )
  )
  with check (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = topics.session_id and s.user_id = auth.uid()
    )
  );

create policy topics_delete on fanout.topics
  for delete to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = topics.session_id and s.user_id = auth.uid()
    )
  );
