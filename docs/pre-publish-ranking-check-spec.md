# Pre-publish ranking check (per client) — feature spec for the ar-tools integration

**Status:** Not built. To be implemented **during the ar-tools integration** (it depends on
ar-tools' per-client GSC / rank-tracker data, which doesn't exist in the standalone Fanout app).
Captured here 2026-06-23 so the integration session has the requirement.

## Goal
Before the user accepts a session's final content map, show — **per client** — whether that
client **already ranks in the top 10** for each planned article's **target keyword**, so they can
**skip / deprioritize / "refresh existing page" instead of "new article."** Avoids commissioning
content the client already ranks for.

## Scope
- **All articles**, not just pillars: every **pillar** `target_keyword` **and** every **supporting
  article** primary (target) keyword for the session. (~5 pillars + ~hundreds of supporting per
  session.)
- **Per client** — the client's domain + GSC property come from the **ar-tools client record**
  (the session is run on behalf of a specific client in the integrated app).

## Data sources (priority order)
1. **GSC (preferred, free, real positions):** the client's Google Search Console data already in
   ar-tools. *Inspect the ar-tools schema for the exact tables* — the AR-Internal-Tools DB has
   `gsc_properties`, `gsc_query_page_daily`, `gsc_ingest_storage`, `keyword_index_status`,
   `keyword_market`. Match each cluster target keyword against the client's GSC **query** rows
   (normalize: lowercase, trim, maybe singular/plural) → take the best (lowest) **position** +
   the ranking **page** over a recent window. "Ranked" = position ≤ 10.
2. **Rank-tracker (if GSC misses):** ar-tools `rank_tracker_keywords` / `rank_reports` for
   keywords the client actively tracks.
3. **DataForSEO SERP (fallback for everything still uncovered):** the Fanout app's existing
   `app/dataforseo` client already does location-aware (`session.location_code`) organic SERP.
   Fetch top-10, normalize result domains (strip protocol/`www`/subdomain), mark "ranked" if the
   **client domain appears on any page** in the top 10 (any-page is the useful signal, not just
   the exact pillar URL).

## Per-keyword output
`{ cluster_id, keyword, ranked: bool, position: int|null, url: str|null, source: "gsc"|"rank_tracker"|"dataforseo" }`
Persist on the session (or cluster) so the architecture/cluster review can render it without
re-fetching; cache with a short TTL (rankings drift).

## Where it surfaces
A badge per article in the Architecture / Cluster review (the existing Fanout views, once ported):
*"Already ranking #4 (GSC)"* (green) vs *"Not in top 10."* Plus a per-session rollup ("18 of 315
already rank top-10") and a bulk action to **exclude / mark-as-refresh** the already-ranking ones
before the client sees the final plan. Run on-demand (a "Check current rankings" button) and/or
automatically right after architecture generation.

## Performance / cost
- **GSC + rank-tracker = DB reads (free, fast).** Do these in **one bulk query** per source
  (fetch the client's tracked queries/positions once, match in memory against the session's
  keywords) — not per-keyword.
- **DataForSEO only for the residue** (keywords not covered by GSC/rank-tracker). For a session
  where the client tracks little, that could be up to ~hundreds of SERP calls (~$1+), so:
  **batch + run async** (reuse the Fanout pipeline's background-job + `ContextThreadPoolExecutor`
  pattern), bound concurrency, and **cache** results. Make the full DataForSEO sweep opt-in if the
  residue is large; GSC-covered keywords return instantly.

## Matching caveats
- Keyword normalization (case/whitespace; consider light stemming) for GSC query matching.
- Domain normalization for DataForSEO (protocol/`www`/subdomain/trailing slash).
- A SERP/GSC snapshot drifts — show the as-of date; don't treat it as permanent.

## Build location
**ar-tools**, after the Fanout consolidation, so it can read the client's GSC/rank data. The
DataForSEO fallback reuses the Fanout `app/dataforseo` client that comes over with the merge.
