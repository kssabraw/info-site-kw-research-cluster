-- §7.8 — Keyword metrics enrichment. Adds the DataForSEO Labs `keyword_overview`
-- columns to `fanout.keywords` so the Table View / CSV / cost banner can surface
-- per-keyword search volume, CPC, and keyword difficulty (PRD §7.8 / §9.1 / §12).
--
-- All columns are nullable: a session with `settings.enrich_with_metrics=false`
-- (and any rows enriched before this migration ran) carries nulls; the gate +
-- clustering paths never read these, so leaving them null is safe.
--
-- `metrics_updated_at` is a point-in-time snapshot timestamp — volume / CPC drift
-- over time, and we make no attempt to refresh on read.

alter table fanout.keywords
  add column if not exists volume               integer,
  add column if not exists cpc_usd              numeric,
  add column if not exists keyword_difficulty   numeric,
  add column if not exists competition_index    numeric,
  add column if not exists metrics_updated_at   timestamptz;
