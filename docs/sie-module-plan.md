# M12 — SIE Term & Entity Module: Build Plan

**Status:** Draft for owner review (2026-06-12). Nothing built.
**Owner decisions driving this plan (2026-06-12, in-session):**
1. **SIE is in scope** — reopens the §9.11 "Skip SIE in v1" lock. On-page term/
   entity intelligence is required for SEO-competitive output (SurferSEO /
   Clearscope-style modeling of what ranking pages actually use).
2. **Match the PRD exactly on providers** — **ScrapeOwl** (page scraping) and
   **Google Cloud Natural Language** (`analyzeEntities`, NER pass) are
   provisioned as **new services**. The substitution options (DataForSEO
   content parsing / Claude-based extraction) were offered and declined. This
   retires handoff §9.1's "no new third-party deps" line (owner decision).
3. **Sequencing = SIE first:** **M12 = SIE**, **M13 = Writer**
   (`docs/writer-module-plan.md`, re-numbered from M12), **M14 = scheduling +
   link injection**. The first articles ever generated are born term/entity-
   enriched.
4. **Trigger timing (locked 2026-06-12): SIE runs lazily, at write time
   only.** It executes solely as the first stage of generating a specific
   article — M13's `run_article_job` (cache check → run if missing/stale →
   adapt → write), and in M14 each scheduled run does the same at its
   scheduled time. SIE is **never** invoked by the research pipeline
   (`/expand`, `/plan-articles`, `/regate`, `/fanout`, `/architecture` add no
   SIE hooks) and is **not bulk-prefetched** at `Schedule all` time — a
   keyword whose article is never written never incurs SIE spend. The M12
   manual `Term analysis` endpoint (§6) is the **validation surface only**
   (owner-triggered, one cluster at a time), needed because no Writer exists
   yet in M12; it is not an eager-analysis pathway.

**Source of truth:** the SIE PRD — PRD #3 in
`docs/blog-writer-pipeline-bundle.md` (lines ~4236–5820): Modules 1–14, Data
Model, Constraints, Guardrails, MVP Scope (§11 — all 22 "MVP Should Include"
items are in scope here; the 4 "MVP Can Exclude" items are excluded).

---

## 1. What M12 ships

`backend/app/sie/` — the full 14-module pipeline, run **per article keyword**
(a cluster's primary keyword), **lazily at write time** (owner decision #4
above — never during keyword research/planning), producing the PRD's Final
Output Model
(`terms.required[]` with per-zone usage recommendations, `terms.avoid[]`,
`entities` merged with `is_entity`/`recommendation_score`, `word_count`
min/target/max, `target_keyword.minimum_usage`, warnings) — persisted with
**7-day caching** keyed by keyword + location.

Consumer is the M13 Writer adapter (it replaces the flat-keyword `sie_stub`
with this output). Since no Writer exists during M12, M12 ships its own
evaluation surface: an owner-only **`Term analysis`** action per article +
a report view (§6), which is also how SIE quality gets judged at review.

## 2. Module map (PRD → implementation)

| # | Module | Egress | Implementation |
|---|---|---|---|
| 1 | Keyword input (outlier mode, force-refresh) | — | API params; `mode: safe` default |
| 2 | SERP collection (top 20 organic, titles/descs/ranks) | **DataForSEO** (already ours) | Extend `dataforseo/client.py` (`serp_top_results`) — `serp_top_urls` exists but drops metadata |
| 3 | URL classification (12 categories, `content_eligible`) + near-dup detection | LLM | One batched **Haiku** tool-use call (20 results); near-dup = first-500-chars >90% similarity, pure code |
| 4 | Page scraping | **ScrapeOwl** (new) | New `app/sie/scrapeowl_client.py`; JS rendering on; retries; per-page `scrape_status` + failure reasons |
| 5 | Zone extraction (title/meta/H1–H4/paragraphs/lists/tables/FAQ) | — | Pure (`beautifulsoup4`+`lxml`); prefer ScrapeOwl's pre-extracted text when clean (PRD Layer-2 note) |
| 6 | Noise filtering, 5 layers (structural strip, text-density, **cross-page fingerprinting**, heuristics, frequency-anomaly CV<0.1) | — | Pure; Layer 3 mandatory; Layer-4 exclusions preserved for entity extraction |
| 7 | N-gram analysis (uni→quad, **lemmatize before counting**, stopwords from unigrams only, quadgram zone flags) | — | Pure; lemmatizer choice flagged (§9) |
| 8 | Term aggregation + subsumption + coverage gate (3-of-top-10; exceptions: quadgrams-in-headings, rank-1–3 multi-domain, high-confidence entities) | — | Pure; never subsume target-keyword sub-phrases |
| 9 | TF-IDF pre-filter (corpus TF-IDF, threshold 0.005, doubles as scoring input) | — | Pure |
| 10 | Semantic filtering (cosine to keyword, 0.65 with dynamic 0.60/0.70 adjustment; heading-term preservation) | OpenAI embeddings (ours) | Reuse `openai_client.embed`, batched |
| 11 | Entity extraction: **Google NLP** pass 1 (salience ≥0.40, 100KB cap, no batch endpoint) + LLM pass 2 (dedupe/categorize/filter; **may not invent**) | **Google NLP** (new) + LLM | New `app/sie/google_nlp_client.py` (rate-limited, per-page); pass 2 = one **Sonnet** tool-use call |
| 12 | Word-count analysis (p25/p50/p75 over 800–5,000-word eligible pages) | — | Pure |
| 13 | Scoring engine (6 weighted signals, min-max normalized; Required/Avoid only; target-kw auto-include @1.00; quadgram zone multipliers 1.5/1.4/1.2×) | — | Pure |
| 14 | Usage recommendations (per-zone p25/50/75 per 1,000 words → counts at target length; **safe** [3× median outlier exclusion] / aggressive modes; 10-per-1,000 hard cap) | — | Pure |

The heart of the pipeline (modules 5–9, 12–14) is **pure and fully
unit-testable in the sandbox**; egress is confined to four thin clients
(DataForSEO, ScrapeOwl, Google NLP, LLM/embeddings) — same testability shape
as the rest of this app.

## 3. Repo integration

- **Package layout:** `sie/models.py` (Final Output Model, pydantic),
  `sie/serp.py` (M2–M3), `sie/scrapeowl_client.py` + `sie/google_nlp_client.py`
  (new clients, §16.3-logged), `sie/extract.py` (M5–M6), `sie/ngrams.py`
  (M7–M8), `sie/filters.py` (M9–M10), `sie/entities.py` (M11),
  `sie/scoring.py` (M12–M14), `sie/pipeline.py` (orchestration + cache check),
  `sie/cache.py`.
- **Concurrency:** scrape + NLP calls fan out per page via the existing
  `ContextThreadPoolExecutor` (meter + session_id propagate); Google NLP is
  one-document-per-request (PRD constraint) → bounded workers + backoff.
- **Cost metering:** new phase **`sie_analysis`** in the M11 `CostMeter`.
  DataForSEO cost stays real (task envelope); ScrapeOwl per-scrape and Google
  NLP per-unit rates added to the meter as configured estimates (calibrate
  against first invoices, same convention as the LLM rates).
- **Run shape:** background job (`run_sie_job`, `@_metered("sie_analysis")`,
  `raise_if_cancelled` between pages), 202 + poll — house pattern.
- **Locale:** `location_code 2840` / `language_code "en"` constants (the app
  is US/English per the Writer PRD's locale lock).
- **Minimum-page threshold:** <5 content-eligible pages → continue with
  degraded confidence + warning (PRD guardrail), surfaced in the report.

## 4. New services + env (OWNER PREREQUISITE — blocks live validation)

| Service | Env var (Railway project level) | Used by | Billing shape |
|---|---|---|---|
| ScrapeOwl | `SCRAPEOWL_API_KEY` | Module 4 | per-scrape credits |
| Google Cloud NL | `GOOGLE_NLP_API_KEY` | Module 11 pass 1 | per 1,000-char unit |

Provision both before M12's live-validation step (the sandbox can't reach any
egress, so as always the pipeline is validated on the deployed stack). New
**Python libs** (not services): `beautifulsoup4` + `lxml`, a lemmatizer (§9),
a stopword list.

## 5. Schema — migration `2026XXXX_sie_keyword_analyses.sql`

```sql
create table fanout.keyword_analyses (
  id             uuid primary key default gen_random_uuid(),
  keyword        text not null,
  location_code  int  not null default 2840,
  language_code  text not null default 'en',
  outlier_mode   text not null default 'safe' check (outlier_mode in ('safe','aggressive')),
  output_json    jsonb not null,          -- the PRD Final Output Model
  cost_usd       numeric(10,4),
  session_id     uuid references fanout.sessions(id) on delete set null,  -- provenance only
  cluster_id     uuid references fanout.clusters(id) on delete set null,  -- provenance only
  run_date       timestamptz not null default now()
);
create index on fanout.keyword_analyses (keyword, location_code, run_date desc);
```

- **Cache semantics per the PRD:** lookup by keyword+location, fresh if
  `run_date` within 7 days, `force_refresh` bypasses and writes a new row,
  history never deleted. The cache is **cross-session by design** (same
  keyword in two sessions reuses one analysis — that's the point).
- **RLS ON from day one** — this is exactly the table class that produced the
  §8.7 `sie_cache` finding in AR-Internal-Tools (cross-tenant cache, RLS
  forgotten). Policy: service-role mediated writes; owner SELECT; VA SELECT
  **not** granted directly (VAs see SIE-derived data only through their
  session's articles/report endpoint, which the backend mediates). Never
  `using (true)`.

## 6. API + UI (M12 slice, minimal)

Per owner decision #4, this endpoint exists for **M12 validation only** —
single-cluster, owner-triggered. There is deliberately **no** bulk-analyze
action, and no SIE call sites in any research-pipeline job. From M13 on, the
normal invocation path is inside `run_article_job`.

- `POST /sessions/{id}/clusters/{cluster_id}/term-analysis` — **owner-only**
  in M12 (`require_owner`); body `{force_refresh?, outlier_mode?}`; cache hit
  returns 200 with the stored report, miss starts the job (202 + poll).
- `GET /sessions/{id}/clusters/{cluster_id}/term-analysis` — the report
  (RLS/visibility-scoped; 404 until analyzed).
- Frontend: a **`Term analysis`** action per article (Cluster view) opening a
  report view — required terms table (term, score, confidence, zone usage
  ranges, reason), entities, word-count rec, warnings, analyzed/excluded URLs.
  This is the M12 evaluation surface; no Writer wiring yet.

## 7. Cost + latency (per analysis; verify rates at provisioning)

~1 DataForSEO SERP call + 1 Haiku classification + ~10–20 ScrapeOwl scrapes +
Google NLP per eligible page (per-1,000-char billing) + 1 Sonnet entity pass +
1 batched embedding call ≈ **$0.30–$0.60 and ~1–3 min**, then cached 7 days.
Because SIE runs at write time (decision #4), this spend is incurred **only
for articles actually generated, when they're generated** — a 315-article
session that schedules everything spends ≈ **+$100–$190 spread across the
drip window**, not up front; unwritten articles cost nothing. Per-article
worker time becomes SIE (~1–3 min, cache-miss case) + Writer (~30–45s) ≈
**2–4 min/article** — fine under the M14 concurrency cap of 3. M14's
`Schedule all` cost preview must include projected SIE cost for uncached
keywords (the $90 VA approval threshold will trip on smaller batches —
arguably correct behavior).

## 8. Tests (sandbox-runnable)

Pure-module coverage is the bulk: 5 noise layers against HTML fixtures
(incl. cross-page fingerprint on 3+ domains and the CV<0.1 anomaly);
lemmatized n-grams (stopwords-from-unigrams-only, quadgram flags);
subsumption (incl. the never-subsume-target-subphrase rule and the
independent-coverage exception); coverage gate + its three exception classes;
TF-IDF math; min-max normalization (incl. the all-equal→0.5 rule); quadgram
zone multipliers; safe-mode 3× outlier exclusion vs aggressive; the
target-keyword floor-vs-percentile merge (Module 13's higher-of rule); word-
count percentiles with the 800/5,000 filters; near-dup detection. Egress
clients mocked; one end-to-end pipeline test over fixture pages.

## 9. Flagged decisions for owner sign-off

1. **Lemmatizer choice:** recommend `simplemma` (pure-Python, no model
   downloads — Docker/Railway friendly) over spaCy/NLTK. The Writer PRD §13
   requires the Writer's future term audit to use the *same* lemmatizer —
   whatever is chosen here becomes shared.
2. **`keyword_analyses` RLS pattern** (§5): service-role + owner-read,
   VA mediated. Mirrors the lesson from §8.7, but it IS stricter than other
   `fanout` tables — confirm.
3. **M12 UI minimalism:** report view only, owner-only trigger. VA exposure
   arrives implicitly in M13 via generated articles.
4. **Meter rates for ScrapeOwl/Google NLP are estimates** until first
   invoices (same calibration convention as the LLM rates).
5. **Intent-alignment scoring input** uses the PRD's fallback (inferred from
   Module 3 page-category distribution) — we have no dedicated intent module
   at SIE time. (The Writer-side intent classification happens later, in the
   M13 adapter.)

## 10. M12 acceptance

(1) Live run on a real cluster keyword (deployed stack) produces a report:
top-20 SERP analyzed, ≥1 page excluded with reason, required terms with
zone usage ranges + confidence + reasons, entities with categories +
salience, word-count rec, target keyword present at score 1.00 with floor
merge. (2) <5-eligible-pages keyword → degraded-confidence continuation.
(3) Second run within 7 days = cache hit (no spend); `force_refresh` =
fresh row, old row preserved. (4) `sie_analysis` phase appears in
`cost_breakdown` with real DataForSEO + estimated ScrapeOwl/NLP cost.
(5) Pure-module test suite green in sandbox; ruff clean.

## 11. Relationship to M13 (Writer)

The Writer plan (`docs/writer-module-plan.md`) already builds against the
full SIE input schema; its M13 adapter swaps the flat-keyword stub for this
module's output, **invoking SIE lazily as stage 1 of `run_article_job`**
(cache check on `keyword_analyses` → run on miss/stale → adapt → write —
decision #4): `terms.required[]` (+ real per-zone `usage_recommendations`,
`is_entity` → the C6 citable-claim pattern activates), `terms.avoid[]`,
`word_count.target` (cross-validated against the brief budget), entities →
the enrichment lede's entity rule works as written (removing flagged
relaxation Δ4a). The stub remains the documented **fallback** when no
analysis exists (Writer's degraded modes stay intact).
