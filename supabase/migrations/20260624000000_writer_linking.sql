-- M15 slice 1 — internal-linking foundation (handoff §9.3 / §9.5).
--
-- Slugs let an article generated on day 1 link to an article scheduled for day 40 (its
-- URL is knowable from slug + base_url before it exists — "drip-safe by construction").
-- site_base_url makes the injected links absolute (required by the Schedule-all modal).
-- The scheduling tables + the article_outputs.scheduled_article_run_id FK land in the
-- scheduling slice.

alter table fanout.sessions add column site_base_url text;
alter table fanout.clusters add column slug text;

-- The URL is {base}/{silo-slug}/{article-slug}, so a slug only has to be unique within
-- its silo (topic) — two silos may reuse an article-slug since the silo namespaces it.
-- Partial index ignores NULLs so a not-yet-slugged cluster never collides.
create unique index clusters_topic_slug_idx
  on fanout.clusters (topic_id, slug) where slug is not null;
