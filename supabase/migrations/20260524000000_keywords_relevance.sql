-- M4 — Relevance gate. Adds `relevance_score` to `fanout.keywords` (PRD §13):
-- the cosine similarity of a keyword to its parent topic's embedding, computed
-- by the §7.6 relevance gate. Nullable: it's null until the gate runs, and
-- M3-era rows (pre-gate) carry null.
--
-- The keyword_status enum already covers the gate's outcomes
-- ('filtered_relevance', 'filtered_junk'), created in the M3 keywords migration,
-- so no enum change is needed here. Clustering output persists to the existing
-- sessions.statistical_clustering_log jsonb column (created in M1); no new table.

alter table fanout.keywords
  add column relevance_score numeric;
