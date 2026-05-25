-- Generic peer-entity filter inputs (PRD §5.1, §7.6). Grounding (§7.1) emits,
-- per seed, the subject's aliases/nicknames and the peer/competitor entities in
-- its category; the relevance gate drops keywords that name a peer but not the
-- seed. Seed-agnostic — the lists are LLM-generated for whatever the seed is.

alter table fanout.sessions
  add column aliases       text[] not null default '{}',
  add column peer_entities text[] not null default '{}';
