-- M1 Foundation — fanout schema, auth/roles, projects, sessions, workspace_settings.
--
-- Scope is limited to the four tables M1 owns (PRD §15.1). Later milestones add
-- their own tables (topics, clusters, keywords, coverage_gaps, site_architecture,
-- csv_exports) in their own migrations. Do not add them here.
--
-- RLS policies derive from the capability matrix (PRD §11.2) and RLS summary (PRD §13).

-- ---------------------------------------------------------------------------
-- 1. Defensive guard. Fail loud if the fanout schema already exists, since the
--    archived (pre-2026-05-21) implementation may have left remnants. We must
--    never silently overwrite existing objects (PRD §14.3).
-- ---------------------------------------------------------------------------
do $$
begin
  if exists (select 1 from information_schema.schemata where schema_name = 'fanout') then
    raise exception 'fanout schema already exists; aborting to avoid overwriting existing objects. Investigate remnants from the archived implementation before re-running this migration.';
  end if;
end
$$;

-- ---------------------------------------------------------------------------
-- 2. Schema
-- ---------------------------------------------------------------------------
create schema fanout;
grant usage on schema fanout to anon, authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 3. Enums
-- ---------------------------------------------------------------------------
create type fanout.user_role as enum ('owner', 'va');

create type fanout.session_status as enum (
  'pending_approval',
  'rejected',
  'running_pre_review',
  'awaiting_silo_review',
  'running',
  'complete',
  'cancelled',
  'error'
);

-- ---------------------------------------------------------------------------
-- 4. Tables
-- ---------------------------------------------------------------------------
create table fanout.user_profiles (
  user_id      uuid primary key references auth.users (id) on delete cascade,
  display_name text,
  role         fanout.user_role not null default 'va',
  created_at   timestamptz not null default now()
);

create table fanout.projects (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users (id) on delete cascade,
  name       text not null,
  is_scratch boolean not null default false,
  created_at timestamptz not null default now()
);
create index projects_user_id_idx on fanout.projects (user_id);
-- At most one Scratch project per user.
create unique index projects_one_scratch_per_user
  on fanout.projects (user_id) where is_scratch;

create table fanout.sessions (
  id                          uuid primary key default gen_random_uuid(),
  project_id                  uuid not null references fanout.projects (id) on delete cascade,
  user_id                     uuid not null references auth.users (id) on delete cascade,
  seed_keyword                text not null,
  audience_hint               text,
  disambiguation_hint         text,
  detected_audience           text,
  disambiguation_choice       text,
  settings                    jsonb not null default '{}'::jsonb,
  status                      fanout.session_status not null default 'running_pre_review',
  estimated_cost_usd          numeric,
  actual_cost_usd             numeric,
  approval_required           boolean not null default false,
  approval_decided_by_user_id uuid references auth.users (id),
  approval_decision_at        timestamptz,
  approval_note               text,
  statistical_clustering_log  jsonb,
  orchestrator_log            jsonb,
  created_at                  timestamptz not null default now(),
  completed_at                timestamptz
);
create index sessions_project_id_idx on fanout.sessions (project_id);
create index sessions_user_id_idx on fanout.sessions (user_id);

-- Singleton workspace settings (PRD §11.4). id is always 1.
create table fanout.workspace_settings (
  id                               int primary key default 1,
  va_soft_cap_usd                  numeric not null default 5.00,
  owner_cost_confirm_threshold_usd numeric not null default 6.00,
  default_relevance_threshold      numeric not null default 0.62,
  silo_discovery_model             text not null default 'gpt-5.4',
  orchestrator_model               text not null default 'claude-opus-4-7',
  architecture_model               text not null default 'claude-opus-4-7',
  default_embedding_model          text not null default 'text-embedding-3-small',
  updated_at                       timestamptz not null default now(),
  updated_by_user_id               uuid references auth.users (id),
  constraint workspace_settings_singleton check (id = 1)
);

-- ---------------------------------------------------------------------------
-- 5. Helper functions
--    SECURITY DEFINER so they bypass RLS on user_profiles. This avoids infinite
--    recursion when a user_profiles policy needs to read the caller's role.
-- ---------------------------------------------------------------------------
create or replace function fanout.current_user_role()
returns text
language sql
stable
security definer
set search_path = fanout, public
as $$
  select role::text from fanout.user_profiles where user_id = auth.uid();
$$;

create or replace function fanout.is_owner()
returns boolean
language sql
stable
security definer
set search_path = fanout, public
as $$
  select coalesce(
    (select role = 'owner' from fanout.user_profiles where user_id = auth.uid()),
    false
  );
$$;

revoke all on function fanout.current_user_role() from public;
revoke all on function fanout.is_owner() from public;
grant execute on function fanout.current_user_role() to authenticated, service_role;
grant execute on function fanout.is_owner() to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 6. Table grants. RLS still enforces row-level scope for `authenticated`;
--    `service_role` bypasses RLS and is used by the backend for admin writes.
-- ---------------------------------------------------------------------------
grant select, insert, update, delete on fanout.user_profiles to authenticated;
grant select, insert, update, delete on fanout.projects      to authenticated;
grant select, insert, update, delete on fanout.sessions       to authenticated;
grant select, update                 on fanout.workspace_settings to authenticated;
grant all on fanout.user_profiles, fanout.projects, fanout.sessions, fanout.workspace_settings
  to service_role;

-- ---------------------------------------------------------------------------
-- 7. Row-Level Security
-- ---------------------------------------------------------------------------
alter table fanout.user_profiles     enable row level security;
alter table fanout.projects          enable row level security;
alter table fanout.sessions          enable row level security;
alter table fanout.workspace_settings enable row level security;

-- user_profiles: owner reads/updates all rows; a user reads/updates only their
-- own. No INSERT/DELETE for authenticated — profiles are provisioned server-side
-- with the service role.
create policy user_profiles_select on fanout.user_profiles
  for select to authenticated
  using ( fanout.is_owner() or user_id = auth.uid() );

create policy user_profiles_update on fanout.user_profiles
  for update to authenticated
  using ( fanout.is_owner() or user_id = auth.uid() )
  with check ( fanout.is_owner() or user_id = auth.uid() );

-- A VA must not be able to change their own role (PRD §13). Enforced with a
-- trigger because an RLS WITH CHECK clause cannot compare OLD vs NEW.
create or replace function fanout.prevent_unauthorized_role_change()
returns trigger
language plpgsql
security definer
set search_path = fanout, public
as $$
begin
  if new.role is distinct from old.role and not fanout.is_owner() then
    raise exception 'only an owner can change a user role';
  end if;
  return new;
end
$$;

create trigger user_profiles_block_self_role_change
  before update on fanout.user_profiles
  for each row execute function fanout.prevent_unauthorized_role_change();

-- projects: owner full access; VA scoped to their own rows. Delete is owner-only.
create policy projects_select on fanout.projects
  for select to authenticated
  using ( fanout.is_owner() or user_id = auth.uid() );

create policy projects_insert on fanout.projects
  for insert to authenticated
  with check ( fanout.is_owner() or user_id = auth.uid() );

create policy projects_update on fanout.projects
  for update to authenticated
  using ( fanout.is_owner() or user_id = auth.uid() )
  with check ( fanout.is_owner() or user_id = auth.uid() );

create policy projects_delete on fanout.projects
  for delete to authenticated
  using ( fanout.is_owner() );

-- sessions: scoped by the session owner (user_id). Delete is owner-only.
create policy sessions_select on fanout.sessions
  for select to authenticated
  using ( fanout.is_owner() or user_id = auth.uid() );

create policy sessions_insert on fanout.sessions
  for insert to authenticated
  with check ( fanout.is_owner() or user_id = auth.uid() );

create policy sessions_update on fanout.sessions
  for update to authenticated
  using ( fanout.is_owner() or user_id = auth.uid() )
  with check ( fanout.is_owner() or user_id = auth.uid() );

create policy sessions_delete on fanout.sessions
  for delete to authenticated
  using ( fanout.is_owner() );

-- workspace_settings: any profiled user may read (the VA wizard needs the soft
-- cap and locked defaults); only the owner may update. No insert/delete (seeded).
create policy workspace_settings_select on fanout.workspace_settings
  for select to authenticated
  using ( fanout.current_user_role() is not null );

create policy workspace_settings_update on fanout.workspace_settings
  for update to authenticated
  using ( fanout.is_owner() )
  with check ( fanout.is_owner() );

-- ---------------------------------------------------------------------------
-- 8. Seed data
-- ---------------------------------------------------------------------------
-- Singleton workspace settings row with v1.7 defaults (PRD §11.4).
insert into fanout.workspace_settings (id) values (1);

-- Seed the Owner profile for Kyle (PRD §14.3). Resolved by email so we never
-- hardcode a generated UUID; no-op if the auth user is absent.
insert into fanout.user_profiles (user_id, display_name, role)
select id, 'Kyle', 'owner'
from auth.users
where email = 'kssabraw@gmail.com'
on conflict (user_id) do nothing;
