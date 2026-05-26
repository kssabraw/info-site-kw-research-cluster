-- M6 — Site architecture generation (PRD §7.11, §13).
--
-- The final pipeline step. After article planning (§7.10) produces clusters,
-- Opus 4.7 writes a pillar overview per silo and the internal linking matrix is
-- assembled, persisting one architecture per session. M6 owns this table.
--
-- One architecture per session, so `session_id` is the PK — a re-generate
-- (PRD §9.3 "Regenerate architecture") upserts in place rather than versioning.
-- The whole pillar/supporting/links structure lives in `architecture_json`; it's
-- a derived artifact (regeneratable from clusters), so there's no normalized
-- pillar/link table to keep in sync.

create table fanout.site_architecture (
  session_id        uuid primary key references fanout.sessions (id) on delete cascade,
  architecture_json jsonb not null,
  generated_at      timestamptz not null default now(),
  is_user_edited    boolean not null default false
);

grant select, insert, update, delete on fanout.site_architecture to authenticated;
grant all on fanout.site_architecture to service_role;

alter table fanout.site_architecture enable row level security;

-- Visible/editable to the Owner (all) or the session's owner. Mirrors the
-- sessions policy, joined through session_id (PRD §13 RLS summary).
create policy site_architecture_select on fanout.site_architecture
  for select to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = site_architecture.session_id and s.user_id = auth.uid()
    )
  );

create policy site_architecture_insert on fanout.site_architecture
  for insert to authenticated
  with check (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = site_architecture.session_id and s.user_id = auth.uid()
    )
  );

create policy site_architecture_update on fanout.site_architecture
  for update to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = site_architecture.session_id and s.user_id = auth.uid()
    )
  )
  with check (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = site_architecture.session_id and s.user_id = auth.uid()
    )
  );

create policy site_architecture_delete on fanout.site_architecture
  for delete to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = site_architecture.session_id and s.user_id = auth.uid()
    )
  );
