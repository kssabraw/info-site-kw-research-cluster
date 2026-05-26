-- M7b — Session Browser mutations (PRD §9.4). Adds a soft-archive flag so a
-- session can be hidden from the default browser list without destroying its
-- data (delete is a separate, explicit action). Existing sessions RLS already
-- covers this column; no new policy needed.

alter table fanout.sessions
  add column if not exists archived boolean not null default false;

create index if not exists sessions_project_archived_idx
  on fanout.sessions (project_id, archived);
