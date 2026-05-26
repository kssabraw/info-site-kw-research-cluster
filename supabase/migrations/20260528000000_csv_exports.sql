-- M10 — CSV export & storage (PRD §12, §13).
--
-- Tracks every CSV snapshot a user generates: who exported which session in
-- which format, and where the frozen file lives in Supabase Storage. The live
-- UI always reads Postgres; each download additionally writes an immutable
-- snapshot to the private `csv-snapshots` bucket and records a row here so the
-- per-session "Exports" tab can list + re-download past snapshots (PRD §12).
-- M10 owns this table.
--
-- The Storage bucket `csv-snapshots` (private) is created out-of-band via the
-- Supabase MCP (buckets are infra, not SQL migrations).

create type fanout.csv_export_format as enum (
  'flat',
  'topic_grouped',
  'architecture'
);

create table fanout.csv_exports (
  id           uuid primary key default gen_random_uuid(),
  session_id   uuid not null references fanout.sessions (id) on delete cascade,
  user_id      uuid not null references auth.users (id) on delete cascade,
  format       fanout.csv_export_format not null,
  -- Object key within the `csv-snapshots` bucket; the backend re-signs a
  -- time-limited URL from it on each download (PRD §12).
  storage_path text not null,
  generated_at timestamptz not null default now()
);
create index csv_exports_session_id_idx on fanout.csv_exports (session_id);

grant select, insert, update, delete on fanout.csv_exports to authenticated;
grant all on fanout.csv_exports to service_role;

alter table fanout.csv_exports enable row level security;

-- Visible to the Owner (all) or the user who owns the parent session (PRD §13
-- RLS summary). Scoped through `sessions` so a VA sees only their own sessions'
-- exports — mirrors the keywords / site_architecture policies. INSERTs are gated
-- by the same scope (a user can only record an export for a session they own).
create policy csv_exports_select on fanout.csv_exports
  for select to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = csv_exports.session_id and s.user_id = auth.uid()
    )
  );

create policy csv_exports_insert on fanout.csv_exports
  for insert to authenticated
  with check (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = csv_exports.session_id and s.user_id = auth.uid()
    )
  );

create policy csv_exports_update on fanout.csv_exports
  for update to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = csv_exports.session_id and s.user_id = auth.uid()
    )
  )
  with check (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = csv_exports.session_id and s.user_id = auth.uid()
    )
  );

create policy csv_exports_delete on fanout.csv_exports
  for delete to authenticated
  using (
    fanout.is_owner()
    or exists (
      select 1 from fanout.sessions s
      where s.id = csv_exports.session_id and s.user_id = auth.uid()
    )
  );
