-- Persist the per-keyword embedding the relevance gate already computes (PRD
-- §7.6), so display-time within-cluster deduplication can run cosine over the
-- stored vectors without paying a fresh embedding pass on every Cluster View.
--
-- Nullable: existing rows stay null and new gate runs populate it for `active`
-- keywords (the same set §7.9 clustering already keeps embeddings for). The
-- dedup falls back to surface-form-only when the column is null, so old
-- sessions still benefit from the cheap half.

alter table fanout.keywords
  add column if not exists embedding public.vector(1536);
