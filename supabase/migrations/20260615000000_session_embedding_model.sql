-- Tag each session with the embedding model that produced its stored vectors,
-- so the app never compares vectors across embedding spaces after the OpenAI ->
-- Gemini provider swap (locked-decision override 2026-06-15).
--
-- text-embedding-3-small and gemini-embedding-001 are both 1536-dim but live in
-- different vector spaces; cosine between them is meaningless. New sessions are
-- tagged at creation with the active model (app.llm.active_embedding_model); the
-- embedding-dependent re-op endpoints (expand / regate / fanout / plan-articles /
-- architecture) refuse a session whose tag != the active model ("freeze old
-- sessions"). Existing rows are all OpenAI-space, so the default backfills them
-- correctly. `fanout.sessions` already carries the §13 RLS policies — no RLS change.

alter table fanout.sessions
  add column if not exists embedding_model text not null
    default 'text-embedding-3-small';
