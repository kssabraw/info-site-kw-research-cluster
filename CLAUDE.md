# CLAUDE.md

This file is read automatically by Claude Code at the start of every session. It contains the persistent context, locked decisions, and rules that apply to **every** milestone in this build. Read it first, then the PRD.

---

## What this project is

The **Topic Fanout Tool** is a keyword research and niche-site architecture planning app. Given a single seed keyword, it produces a complete content map for a niche authority site: silos (top-level subfolders), articles within each silo with target keywords, and an internal linking structure. (H2 outlines were moved out of the planning pipeline on 2026-06-09 — the writer module (M12+) generates them at write time; `clusters.h2_outline` persists empty until then.)

The PRD is the source of truth for everything: **`docs/topic-fanout-prd-v1_7.md`** (or the highest version number present in `docs/`). Read it in full before doing significant work. When the PRD conflicts with what you'd otherwise suggest, the PRD wins.

---

## Repo context

This repo was **reset on 2026-05-21** after a previous 12-phase implementation was archived. The reset is intentional. Treat the repo as empty:

- Do not try to recover code from the archived implementation.
- Do not pattern-match the previous "12-phase" architecture; this build uses a different design (silos → article planning orchestrator → architecture) per the PRD.
- A git bundle of the old code exists separately for human reference only.

---

## Locked architectural decisions

These don't change session-to-session. Don't propose alternatives.

| Layer | Choice |
|---|---|
| Source repo | `kssabraw/info-site-kw-research-cluster` (monorepo: `backend/`, `frontend/`, `supabase/`, `docs/`) |
| Backend | FastAPI (Python 3.11) on Railway, project `AR Tools`, service `info-site-kw-research-cluster` |
| Frontend | React + Vite + TypeScript, deployed to Netlify from `/frontend` |
| Database | Supabase shared with AR Tools, **all tables isolated under the `fanout` schema** |
| Auth | Supabase Auth, role-based access via `fanout.user_profiles.role` (owner / va) |
| LLM (silo discovery) | OpenAI `gpt-5.4` with browsing |
| LLM (article-planning orchestrator) | Anthropic `claude-opus-4-7` with tool-use mode for strict-schema JSON |
| Site architecture | **Deterministic, LLM-free** since 2026-06-09 (per-pillar Opus call removed, owner decision; the writer module owns pillar titles/summaries — flagged divergence from PRD §7.11) |
| LLM (writer module, M14+) | Anthropic `claude-sonnet-4-6` for prose calls + `claude-haiku-4-5` for short/classification calls (locked 2026-06-09 §9.11; tiering per Writer PRD §17, 2026-06-12) |
| Embeddings | **Google `gemini-embedding-001` @ 1536-dim (Matryoshka)** via Google AI Studio (`GEMINI_API_KEY`) — owner override 2026-06-15 (whole-app, quality/consistency), supersedes the prior OpenAI `text-embedding-3-small` lock. Pluggable behind `embedding_provider` (default `openai`); ships **dormant** until the key is provisioned + the cosine thresholds are recalibrated on live Gemini runs, then flip `EMBEDDING_PROVIDER=gemini`. 1536-dim truncation keeps the `vector(1536)` schema; vector spaces must not be mixed across providers (per-session `embedding_model` guard). |
| External data | DataForSEO (Labs + SERP + Keyword Data) |
| SIE module (M12) | **ScrapeOwl** (page scraping, PRD-exact) + **TextRazor** (entity-extraction NER pass — owner amendment 2026-06-12, replacing the initially chosen Google Cloud NLP; the PRD's grounded-NER Module-11 design is preserved) — newly provisioned services (substitutions declined). **Runs lazily at write time only** — stage 1 of generating a specific article; never during keyword research/planning, never bulk-prefetched (owner decision 2026-06-12) |
| Clustering | NetworkX + python-louvain |

API keys (DataForSEO, OpenAI, Anthropic, Supabase) are already configured at the Railway project level and inherited by this service. No new keys need provisioning.

---

## Milestone discipline

The build is sequenced into 11 milestones (M1–M11) defined in PRD §15.1. **All eleven are complete and merged.** Post-v1 milestones (M12+ — Blog Writer integration, planned in `handoff.md` §9.10) follow the same discipline. **Build one milestone at a time.** After each, stop and wait for human review before starting the next.

Rules that apply to every milestone:

- **Don't pre-build for later milestones.** Tempting optimizations like "I'll add the keywords table now since we'll need it in M3" are out of scope. Each milestone owns its schema additions.
- **One feature branch per milestone**, named `m{N}-{short-name}` (e.g., `m1-foundation`, `m2-silo-discovery`). Don't push directly to `main`.
- **Logical commits within a milestone** (separate commits for schema, backend, frontend, etc.) rather than one giant commit.
- **End-of-milestone summary** is required: what was built, decisions made on ambiguous points, anything to flag for human review, and verification steps.

The active milestone is tracked at the bottom of this file (`## Active milestone`). Update it when transitioning.

---

## Working style

**Match existing patterns where you can see them.** The Dockerfile pattern for the backend should mirror `services/nlp` in the `showup-local` repo per PRD §14.2. For things you can't see (existing schemas in shared Supabase, conventions in other AR Tools services), ask before assuming.

**Supabase migrations:**
- One file per migration, named `2026XXXX_{description}.sql`, under `supabase/migrations/`.
- All tables go under the `fanout` schema. Never create tables in `public`.
- Use **real** RLS policies derived from PRD §11.2 (capability matrix) and §13 (RLS summary). **Never** use `using (true)` placeholders.
- Add a defensive check at the top of the M1 migration that fails loud if the `fanout` schema already exists (the previous archived implementation may have left remnants).

**Structured logging from day one.** Use `python-json-logger` or equivalent. The log shape is defined in PRD §16.3. Every external API call gets logged with cost, latency, and correlation_id.

**Frontend conventions:**
- Use TanStack Query for server state.
- No browser storage APIs for app data — everything goes through the backend to Supabase.
- Components in `/frontend/src/owner/` (Owner UI) and `/frontend/src/va/` (VA wizard) are separate; shared code goes in `/frontend/src/shared/`.

**When PRD ambiguity surfaces:**
- Flag it, pick the most conservative interpretation, and mention it in the end-of-milestone summary.
- Don't silently guess.
- PRD open questions Q2–Q18 are tuning values for later milestones (relevance thresholds, SERP overlap thresholds, etc.). None of them block any milestone's structural work; flag if one appears to.

---

## Never

- Never propose alternatives to the locked decisions above.
- Never create tables outside the `fanout` schema in Supabase.
- Never use `using (true)` RLS policies.
- Never reference or try to recover the archived previous implementation.
- Never push directly to `main`. Always go through a feature branch.
- Never pre-build work that belongs to a later milestone.
- Never store sensitive data in logs (API keys, user passwords, raw service_role tokens).
- Never bypass the cost cap / approval workflow for VA-initiated sessions.

---

## Key file locations

| Path | What's there |
|---|---|
| `docs/topic-fanout-prd-v1_7.md` | The PRD (current version). Always read before significant work. |
| `docs/blog-writer-pipeline-bundle.md` | **The AR Tools Blog Writer PRD bundle** (all 8 PRDs concatenated, verbatim) — the source of truth for the M12–M14 content-generation integration (`handoff.md §9`). Landed 2026-06-12. PRD #3 (SIE) = M12; PRD #2 (Brief Generator v2.3) = M13; PRD #1 (Writer v1.7, with §17 Call Inventory / §18 Prompt Scaffolds / §20 golden example) = M14. Read before drafting any SIE/Brief-Gen/Writer code. |
| `docs/blog-writer-live-contract.md` | Ground-truth writer **I/O contract** recovered from the AR-Internal-Tools prod DB. Reconciles against the bundle; **where the two disagree, the live contract wins** (e.g. brief runs v2.6 in prod vs v2.3 in the PRD). |
| `docs/sie-module-plan.md` / `docs/brief-generator-module-plan.md` / `docs/writer-module-plan.md` | The **M12 (SIE)**, **M13 (Brief Generator)**, and **M14 (Writer)** build plans, reconciled against the bundle (2026-06-12). Each carries flagged decisions awaiting owner sign-off (SIE §9, Brief Gen §7, Writer §8). |
| `handoff.md` | Session-continuity doc: live state, the §2 live-validation checklist, deploy/infra gotchas (§3), and the post-v1 plans (§8 site creation, §9 Writer integration). **Its dated entries are newer than the milestone history below — where they conflict, `handoff.md` wins.** |
| `docs/` | Historical PRD versions and supplementary design docs. |
| `backend/app/main.py` | FastAPI entry point. |
| `backend/app/pipeline/` | Pipeline orchestration (silo discovery → architecture). |
| `backend/app/llm/` | OpenAI + Anthropic client wrappers. |
| `backend/app/dataforseo/` | DataForSEO client. |
| `backend/app/storage/` | Supabase client wrappers (RLS-aware). |
| `backend/Dockerfile` | Railway deploy target. |
| `frontend/src/owner/` | Owner three-view UI. |
| `frontend/src/va/` | VA wizard. |
| `frontend/src/shared/` | Shared components, auth, API client. |
| `supabase/migrations/` | All schema migrations. One file per migration, never edit historical migrations. |

---

## Common commands

(Populated as the build progresses. M1 establishes the initial set.)


```bash
# Backend: run locally
cd backend && uvicorn app.main:app --reload

# Backend: deploy to Railway
railway up --service info-site-kw-research-cluster

# Frontend: run locally
cd frontend && npm run dev

# Frontend: build for production
cd frontend && npm run build

# Supabase: apply pending migrations
supabase db push

# Supabase: generate types from current schema
supabase gen types typescript --project-id <ref> > frontend/src/shared/db-types.ts
```


---

## Active milestone

**v1 MVP — complete. M11 is merged to `main` and deployed (M1–M11 all built,
all live).** State as of 2026-06-11; `handoff.md`'s dated entries are the live
log and supersede the per-milestone history below where they conflict.

**Post-M11 work already shipped to `main` + deployed (2026-06-09, owner
decisions; nothing mid-flight):**
- **M11 confirmed working in prod** (live sessions carry real `actual_cost_usd` +
  per-phase `cost_breakdown`). Two cost fixes landed: the Opus meter rate in
  `cost_meter.py` recalibrated **(15, 75) → (5, 25)** USD/1M tok (the flagged
  estimate was 3× high), and `estimated_cost_usd` is now persisted on **every**
  run path (`POST /expand` writes it at claim time; it was previously only
  written by submit-for-approval, leaving the cost banner with no estimate on
  owner / under-cap VA runs).
- **§7.8 metrics enrichment is now BUILT** (migration `keyword_metrics`, shipped
  2026-05-29) — every "metrics unbuilt / toggle decorative" flag in the history
  below is **stale**.
- **Writer-ownership refactor:** the M5 orchestrator no longer emits
  `suggested_h2s`, and **site architecture is fully deterministic / LLM-free**
  (the per-pillar Opus call removed, −208 lines; the writer module owns pillar
  title/summary + all H2s at write time; the owner H2-edit API is closed).
  Until M12 ships, the Architecture view + architecture-CSV `outline_h2s` are
  intentionally blank. Flagged divergence from PRD §7.10/§7.11.
- **Internal links capped at ≤5/page:** pillar = ≤3 down-links (most-central
  children) + ≤2 pillar laterals; article = 1 up-link + ≤4 laterals, one lateral
  slot being the within-silo article cycle (i→i+1, last→first) — the new
  no-orphan guarantee. A runtime `link_health()` audit (orphans/dangling, 0 by
  construction) persists in `architecture_json`, surfaces in the Debug view +
  Architecture toolbar. Live-verified on session `790f750f`. Applies to newly
  generated architectures (regenerate to apply retroactively).
- **All 14 `fanout` migrations confirmed applied to prod** (sweep query in
  `handoff.md`), after a code-before-migration gap (`filtered_language` enum)
  failed a live run (~$3.94 spent, correctly metered on failure, 0 keywords
  persisted). **Lesson: applying a new migration to prod via Supabase MCP is
  part of the deploy** — the repo file alone doesn't touch the live DB.

**What remains (in order):**
1. **Finish the live-validation checklist in `handoff.md` §2** — M8 (VA
   routing + wizard), M9 (approval round-trip), M10 (Storage upload +
   signed-URL download), and the open M11 items (e.g. nested-thread
   `external_call` logs carrying `cost_usd` + non-null `session_id` on a fresh
   post-redeploy run). Partially done: the meter and §16.4
   partial-cost-on-failure are live-confirmed.
2. **Post-v1 sequence re-set 2026-06-12 (owner decisions, revised twice same
   day): M12 = SIE Term & Entity module → M13 = Brief Generator → M14 =
   Writer foundation → M15 = scheduling + link injection** (`handoff.md`
   2026-06-12 dated entries + §9.10). **Brief Gen + SIE both run lazily at
   write time only** (parallel stage 1 of generating a specific article —
   never during keyword research, never bulk-prefetched; per-article ≈
   $0.92–$1.96, ~3–5 min on cache miss). The AR Tools Blog Writer PRD bundle
   landed in `docs/blog-writer-pipeline-bundle.md` (2026-06-12, all 8 PRDs
   verbatim — the §9.13 fetch is satisfied); all three build plans are
   drafted and reconciled against it:
   **`docs/sie-module-plan.md`** (M12 — full 14-module SIE port; **PRD-exact
   providers: ScrapeOwl + TextRazor, newly provisioned services** (owner
   decision, overriding the earlier "no new third-party deps" framing; NER
   provider amended Google NLP → TextRazor same day);
   `fanout.keyword_analyses` 7-day cache with RLS on from day one),
   **`docs/brief-generator-module-plan.md`** (M13 — full Brief Gen v2.3
   Steps 0–11 at write time; **zero new services** — Reddit + the 4-LLM
   fan-out are DataForSEO endpoints; `text-embedding-3-large` inside the
   module; Step 12 silo-identification skipped; `fanout.briefs` 7-day
   cache), and **`docs/writer-module-plan.md`** (M14 — Writer in
   `1.7-no-context` + `no_citations` degraded mode; Sonnet 4.6 prose /
   Haiku 4.5 short calls; Brief Gen output IS Writer Input A, so the heading
   structure comes from the real Brief Gen — resolving the empty-`h2_outline`
   gap). **Owner prerequisite before M12 live validation: ✅ DONE 2026-06-15 —
   `SCRAPEOWL_API_KEY` + `TEXTRAZOR_API_KEY` provisioned on the
   `info-site-kw-research-cluster` Railway service.** Open: plan-level flags awaiting sign-off (SIE plan §9 — incl.
   the lemmatizer choice, shared with the Writer's future term audit;
   brief-gen plan §7 — incl. the v1.7-§5 Step-2 spec gap and the DataForSEO
   "LLM Responses" availability check; writer plan §8).
3. **Before M14 (Writer) ships:** address the `handoff.md` §8.7 security finding —
   `AR-Internal-Tools.public.sie_cache` has **RLS disabled**. Don't enable it
   blind (the writer service's reads would break without a policy); coordinate
   with the AR-Internal-Tools owner.

**M11 — Cost confirmation + observability (PRD §15.1 / §16): complete & merged
to `main`, deployed (live by 2026-06-09; meter confirmed working in prod — see
the lead block above for the post-merge corrections).** Built on
`claude/exciting-davinci-tZGwH` (this
session's pinned branch, off `main` at the M10 merge `4b10ed2`). Backend **176
tests pass** (165 prior + 11 new in `tests/test_cost_meter.py` + the owner-only
`/debug` role test), ruff clean, import smoke OK; frontend builds strict-clean
(tsc + vite). **Live cost numbers, the banner, and the debug view are NOT
sandbox-validated** (egress blocked) — validate on the deployed stack.

**What shipped (per §16.3 / §16.4 / §15.1 / §15.3 #7–#8):**
- **Real-metered per-step cost → `actual_cost_usd` + a new `cost_breakdown` jsonb,
  flushed live (§16.4).** A per-run `CostMeter` (`app/cost_meter.py`) accumulates
  each external call's cost, broken down by pipeline phase. **DataForSEO cost is
  the real per-call charge** from its task envelope (`task["cost"]`); **LLM cost is
  derived from real response token usage** via a rate table (Opus 15/75, gpt-5.4
  5/15 per 1M tok — *rates are estimates, flagged for calibration*; embeddings
  0.02/1M). *[Stale: the Opus rate was recalibrated to (5, 25) on 2026-06-09 —
  see the lead block.]* The background jobs (`app/cost_attribution.py::metered_run`) bind the
  meter, spawn a daemon that flushes `actual_cost_usd` + `cost_breakdown` every
  `cost_flush_interval_s` (=10s, §16.4), and do a final lock-serialized flush on
  exit (incl. on failure → partial cost persists). Silo discovery (synchronous in
  `POST /sessions` / `/disambiguate`) is metered via `metered_sync` so the session
  total covers the full §8.1 run. **Cost accumulates across a session's runs**
  (expand→plan→architecture, plus re-plan/regate/fanout each *add* their spend) —
  the honest cumulative figure §16.4 calls "the session's running cost".
- **Context propagation fix (`app/concurrency.py`).** The pipeline parallelizes
  API calls in raw `ThreadPoolExecutor`s, which **don't** copy contextvars into
  workers — so the meter (and the §16.3 `session_id`/`correlation_id`) were
  invisible in the very threads making the dominant DataForSEO calls.
  `ContextThreadPoolExecutor` captures the caller's context at submit time;
  swapped in via an import alias across `expansion.py` / `competitor.py` /
  `serp.py` / `orchestrate_articles.py` / `architecture/generate.py` (no other
  call-site changes). **Side benefit:** nested-thread external-call logs now carry
  `session_id`, closing a latent §16.3 gap.
- **Structured logs completed (§16.3).** The four external-call sites
  (`dataforseo/client.py`, `llm/openai_client.py` `_respond` + `embed`,
  `llm/anthropic_client.py`) now populate the `cost_usd` field (was `None  #
  populated in M11`) and feed the meter; the context fix gives them real
  `session_id`/`correlation_id`.
- **Live cost banner (§8.4 / §15.1).** `GET /summary` now carries a `cost` block
  (`estimated_cost_usd`, `actual_cost_usd`, `breakdown`) in **both** the cheap
  running payload and the full one, so the banner climbs as the job flushes. New
  `shared/CostBanner.tsx` (actual vs. estimate + a progress bar; turns red when
  actual exceeds the non-binding estimate) on the Owner workspace **and** the VA
  wizard progress screen. VA sees own cost only (RLS-scoped via the session).
- **Owner debug view (§15.3 #8).** `GET /sessions/{id}/debug` (**require_owner** —
  a VA gets 403; still RLS-scoped to a visible session) returns
  `statistical_clustering_log` + `orchestrator_log` + the cost attribution. New
  Owner-only `owner/DebugView.tsx` at `/session/:id/debug` (a "Debug" link in the
  workspace head, owner-only; **not** in the VA surface) renders the per-step cost
  table + the raw logs. The data already persisted — this is read + gate + render.
- **Migration `20260529000000_session_cost_breakdown.sql`** (adds `sessions.
  cost_breakdown jsonb`; no RLS change — `sessions` already carries the §13
  policies) **applied to the live DB via Supabase MCP** (verified: column present,
  RLS still enabled). `actual_cost_usd` / `statistical_clustering_log` /
  `orchestrator_log` already existed from M1.

**M11 decisions / divergences (flagged for review):**
- **LLM $/token rates are estimates** (DataForSEO cost is real). So the §15.3 #7
  "±25% of §8.1" check is honest on the DataForSEO-dominated total but carries LLM
  estimation error until the rates are calibrated against real OpenAI/Anthropic
  invoices after the first ~10 production runs (same caveat as `cost.py`).
- **§7.8 metrics enrichment is still unbuilt** *[Stale: metrics shipped
  2026-05-29 (`keyword_metrics` migration) — the "+metrics" §15.3 #7 line CAN now
  be exercised]*, so §15.3 #7's literal "standard +
  metrics **on**" scenario can't be exercised as written; validate at metrics-off
  and treat the +metrics line as estimate-only. Flagged.
- **`cost_breakdown` is keyed by pipeline *phase* (job)** — `silo_discovery`,
  `expand`, `article_planning`, `architecture`, `regate`, `recursive_fanout` — not
  by §8.1 line item. Finer per-endpoint cost lives in the per-call structured logs
  (each carries `service`/`endpoint`/`cost_usd`). Threading line-item step labels
  deep into the pipeline functions was judged too invasive for the value. Flagged.
- **Cost is cumulative across re-runs.** A re-plan / regate / fanout *adds* to
  `actual_cost_usd` and its phase in `cost_breakdown` (real money was spent), so a
  re-planned session can read above the one-shot §8.1 estimate, and the
  `article_planning` phase can exceed its single-run figure. Truthful but flagged.
- **Final-flush ordering** is made safe with a per-run flush lock (once `stop` is
  set the loop starts no new flush; the final flush blocks on the lock until any
  in-flight periodic flush finishes, then writes the latest value last). A
  process restart mid-job still strands `status='running'` (the standing M5
  durable-queue caveat) — the last periodic flush is the recorded partial cost.
- **Owner calibration tools** (`/routing-diagnostic`, `/cluster-preview`,
  `/lever3-simulate`) run their embedding calls synchronously in the request with
  **no meter bound**, so their (cheap, embedding-only) spend is not attributed to
  the session. Acceptable — they're read-only analysis, not part of a run's cost.
  Flagged.
- **Background jobs' `correlation_id` continuity** into the job is unchanged
  (pre-existing): jobs bind `session_id` (the primary §16.3 key) but inherit no
  request `correlation_id`, since `jobs._EXECUTOR` is left a plain executor.
  Low; not re-architected (out of M11's "don't re-architect existing logging").

---

**M10 — CSV export (PRD §15.1 / §12): complete & merged to `main`
(2026-05-28, per owner instruction).** Built on `claude/wonderful-allen-oTKaO`
(this session's pinned branch — *not* an `m10-…` branch, per the session task
instruction), merged `--no-ff` (remote `main` was at the M9 merge `1e0db30`; the
merge added the M10 commits cleanly, no conflicts). Backend **165 tests pass**
(139 prior + 14 csv-builder + 12 export-API), ruff clean, import smoke OK; frontend
builds strict-clean (tsc + vite). **Storage upload, signed URLs, and the live
download round-trip are NOT validated** (sandbox egress blocked, standing
constraint) — validate on the deployed stack (checklist in `handoff.md §2`).

**Three formats, generated live from current Postgres state** (so user edits /
exclusions are reflected), all built by **pure functions** in
`backend/app/csv_export.py` (fully unit-tested, no egress):
- **flat** — one row per keyword, the §9.1 Table View columns (keyword, topic,
  cluster, source(s), volume, kd, cpc, relevance, status). **Volume/KD/CPC stay
  blank** (metrics enrichment §7.8 unbuilt; those columns don't even exist on the
  `keywords` table yet).
- **topic_grouped** — "one CSV per topic" (§12) delivered as a **single `.zip`** of
  per-topic CSVs (one zip = one `storage_path`). *Decision flagged.*
- **architecture** — one row per page (pillar or supporting article):
  `page_type, title, target_keyword, parent_pillar, outline_h2s,
  internal_links_out`. Link/title cols are **name-resolved** (article names, pillar
  titles) not raw ids. Requires a generated `site_architecture` — **400** if none.

**Storage + signed URLs (deploy-only path, `backend/app/storage/exports.py`):** the
**backend** uploads the snapshot to the private **`csv-snapshots`** bucket under
`{user_id}/{session_id}/{ts}-{rand8}.{ext}` (the random suffix prevents two
concurrent same-microsecond exports overwriting each other) via the **service
client**, then serves the download via a **time-limited signed URL** it mints
(`csv_signed_url_ttl_s`, default 3600s). The frontend never touches Storage
directly (CLAUDE.md "no browser storage APIs"). Re-download **re-issues a fresh
signed URL** (an old one may have expired). Confirmed the supabase-py service
client's `.storage.from_(...).upload(...)` / `.create_signed_url(...)` are
reachable (the `ClientOptions(schema="fanout")` only scopes PostgREST, not
Storage) — **but this is unverified in the sandbox; deploy-only.**

**Endpoints (`backend/app/api/exports.py`, new router):** `POST
/sessions/{id}/export?format=flat|topic_grouped|architecture` (generate +
snapshot + record + return signed URL — **synchronous**, a few-thousand-row CSV
renders in <1s; `require_user`, both roles, scoped to a visible session); `GET
/sessions/{id}/exports` (the Exports tab list, RLS-scoped); `GET
/exports/{id}/download` (re-sign a fresh URL for a past snapshot, RLS-scoped).
Storage helper `list_surviving_keywords` (paged active/excluded/covered pool) added
to `storage/silo.py`; `csv_signed_url_ttl_s` added to config.

**Schema (`supabase/migrations/20260528000000_csv_exports.sql`, applied live via
MCP):** `fanout.csv_exports` (`id, session_id, user_id, format` enum
`flat`/`topic_grouped`/`architecture`, `storage_path`, `generated_at`) under the
`fanout` schema with **real RLS** (owner all; else session-owner via a
`sessions`-join — mirrors the keywords / site_architecture policies; never
`using (true)`). The private `csv-snapshots` **bucket was created via MCP**
(`insert into storage.buckets … public=false`) — the service role bypasses storage
RLS, so no `storage.objects` policies are needed (frontend only ever sees signed
URLs). Live migration tracking recorded it under an apply-time timestamp (differs
from the repo file prefix, as for every prior migration).

**Frontend:** new **Exports tab** (`frontend/src/owner/views/ExportsView.tsx`,
route `exports`) added to **both** the Owner and VA segmented controls in
`SessionWorkspace` (Export is ✓ for both, §11.2). It offers the three formats as
**Download** buttons (architecture disabled until the summary reports an
architecture) and lists past snapshots with per-row re-download; a generate /
re-download opens the backend-minted signed URL in a new tab (with a `&download=`
filename hint). `shared/api.ts` gained `createExport` / `listExports` /
`downloadExport` + the `CsvExport*` types. Query key `["exports", sessionId]`
(new, no clash); the summary read shares the existing `["summary", sessionId]`.

**M10 decisions / divergences (flagged for review):**
- **"Postgres generates the CSV live" (§12) is implemented as the backend reading
  current Postgres state and building the CSV in Python.** CSV *generation* is a
  pure, side-effect-free function over already-fetched rows (carries all the test
  coverage); the Storage upload + signed-URL step is a thin, separately-mockable
  layer (`storage/exports.py`) — **deploy-only validated.**
- **Synchronous generation** (no background job, unlike the pipeline) — a
  few-thousand-row CSV is fast. Flagged.
- **flat/topic_grouped include the *surviving* pool (active + excluded + covered)**,
  matching `getAllSurvivingKeywords` / the Table View fetch (§12 "matching the data
  shown in the UI"). Gate/orchestrator-discarded rows
  (filtered_relevance/junk/dropped) are excluded. *Note:* the Table View hides
  `excluded` by default (a carried M7 LOW), so the flat CSV is slightly broader than
  the default on-screen view — it's the full surviving pool. Flagged.
- **topic_grouped = a single `.zip`** (one per-topic CSV per entry) so it maps to
  one `storage_path` / one `csv_exports` row, rather than N rows. Flagged.
- **`csv_exports` RLS scopes a VA through `sessions.user_id`** (owner sees all),
  not via `csv_exports.user_id` — consistent with the keywords/architecture
  policies and the §13 "parent project's user_id" intent (a VA only ever exports
  their own sessions anyway).
- **"Export selected to CSV" (§9.1 bulk action) is deferred** — the snapshot model
  is session+format, and an arbitrary keyword subset would need a different
  (non-snapshot) path. The three session-level formats ship; selected-export is
  flagged, not built.
- **Signed-URL TTL = 1h, endpoint returns the URL** (frontend opens it), matching
  §12 "served from Storage" rather than streaming bytes through the API.
- **CSV formula-injection hardening** on every exported text cell (a leading
  `= + - @ \t \r` → prefixed with `'`); numeric columns are formatted by us and
  never trip the guard. Unit-tested.
- **Not browser-validated** — Storage upload / signed URL / live round-trip pending
  on the deployed stack (sandbox egress blocked).

---

**M9 — Approval workflow (PRD §15.1 / §11.3): complete & merged to `main`
(2026-05-26, per owner instruction).** Built on `claude/jolly-heisenberg-Z06PH`
(this session's pinned branch — *not* an `m9-…` branch, per the session task
instruction), merged `--no-ff` (remote `main` was at the M8 sign-off `27f5731`; the
merge added the 6 M9 commits cleanly, no conflicts). **No schema/migration** —
every approval column (`estimated_cost_usd`, `approval_required`,
`approval_decided_by_user_id`, `approval_decision_at`, `approval_note`) and the
`pending_approval`/`rejected` statuses already exist from M1; M9 is logic + UI
only. Backend **139 tests pass** (116 prior + 9 cost + 14 approvals), ruff clean,
import smoke OK; frontend builds strict-clean (tsc + vite). **Still not
browser-validated** (sandbox egress blocked, standing constraint) — validate the VA
submit → Owner approve/reject → VA-sees-decision round-trip on the deployed stack.

**Where the gate sits (the §11.3 ambiguity, resolved conservatively):** §11.3
describes the *whole run* as gated, but in our build silo discovery already runs
synchronously at `POST /sessions` (cheap LLM) and the expensive DataForSEO work is
`/expand`. M9 puts the approval gate at the **cost-bearing `/expand`** — i.e. the
wizard's cost-confirmation step. An approved session then runs `/expand` via the
*same* entry point as a run-now session. Silo discovery + finalize happen before
the gate as they did in M8. Flagged.

**Cost model (`backend/app/cost.py`, pure + unit-tested):** `estimate_cost(...)`
derives a dollar figure from the run config (coverage mode, silo count, deep-mine
count, `recursive_fanout`, `enrich_with_metrics`) using per-component rates
back-derived from the §8.1 table (calibrated at its 5-silo/3-deep-mined reference;
reconstructs the subtotals within a few cents and scales sensibly). Verified:
standard+metrics and comprehensive+metrics land **under** the $5 VA cap; a 10-silo
comprehensive+metrics run and any recursive run land **over** it — exactly the §8.4
intent. `requires_approval(...)` = estimate > soft cap **OR** recursive. Recursive
uses the §7.7 low multiplier (5×) for the headline number (moot for the gate —
recursive always trips it). Rates are module constants to recalibrate after the
first ~10 production runs (per §8.1).

**Backend endpoints (`api/sessions.py`):** `GET /workspace-settings` (soft cap +
locked defaults; require_user, matches the RLS SELECT policy); `GET
/sessions/{id}/cost-estimate?gated_count=N` (authoritative estimate + breakdown +
soft cap + `requires_approval` + triggers; `gated_count` previews the wizard's
not-yet-persisted deep-mine selection, else the persisted count); `POST
/sessions/{id}/submit-for-approval` (stores estimate, sets `pending_approval` +
`approval_required`, clears any prior decision, does **not** start the pipeline;
allowed from `awaiting_silo_review` or `rejected` [resubmit]); `POST
/sessions/{id}/cancel-approval` (→ back to `awaiting_silo_review`); `GET /approvals`
(**owner-only**, the queue, enriched with VA display name + project name + deep-mine
count); `POST /sessions/{id}/approve` (**owner-only**; records decider/time/note,
`try_mark_running` → `submit_expand`); `POST /sessions/{id}/reject` (**owner-only**;
sets `rejected` + note, no pipeline). The `/summary` payload gained an `approval`
block (`required`, `estimated_cost_usd`, `note`, `decided_at`) so the VA's waiting
screen sees the decision; `pending_approval`/`rejected` short-circuit to the cheap
status-only payload like `running`. Storage helpers (`storage/silo.py`):
`get_workspace_settings`, `count_gated_topics`, `list_pending_approvals`. New tests:
`tests/test_cost.py` (9), `tests/test_approvals.py` (14, monkeypatched store like
`test_roles.py`).

**Frontend:** the wizard's **CostStep** now fetches the real estimate (replacing
M8's static `mineEstimate` band) and branches: under cap → **Run now** (unchanged:
`setDeepMine` + `expand`); over cap / recursive → **Submit for approval**
(`setDeepMine` + `submit-for-approval` → new **WaitingStep**). WaitingStep polls
`/summary` every 30s (the §11.3 cadence); on approve the session leaves
`pending_approval` → `running`/`awaiting_article_planning`/`complete` and the
wizard hands off to the existing ProgressStep (which still auto-chains expand →
plan); on reject it shows the Owner's note + an **Adjust & resubmit** path; a
**Cancel request** button calls `cancel-approval`. DeepMineStep now shows the live
server estimate (per-selection-count, React-Query-cached) instead of the static
band. New Owner **Approvals** page (`owner/ApprovalsPage.tsx`, route `/approvals`):
a queue with a decision modal (approve / reject + optional note), 30s polling. The
**AppShell** topbar gained an owner-only **Approvals** link with a pending-count
badge (30s polling, `enabled: isOwner` so a VA never calls the owner-only
`/approvals`). New `api.ts`: `getCostEstimate`, `getWorkspaceSettings`,
`submitForApproval`, `cancelApproval`, `listApprovals`, `approveSession`,
`rejectSession`, the `SummaryApproval` field on `PipelineSummary`.

**M9 decisions / divergences (flagged for review):**
- **Gate at `/expand`, not the whole run** (see above). An approved VA run still
  ends at the article plan (architecture stays owner-only, carried from M8).
- **No "clone into a new draft" on reject** (§11.3 step 7 wording). Instead the
  *same* session is reusable: `submit-for-approval` is allowed from `rejected`, and
  if the VA reduces scope under the cap the CostStep flips to **Run now** and
  `/expand` runs directly from `rejected` (`try_mark_running` allows it). Cloning a
  session means re-running silo discovery; reuse is cheaper + simpler. The VA can't
  change `coverage_mode` without a new session (it's set at creation) — flagged.
- **Approval-queue "submitted at" = the session `created_at`**, not a true
  submission timestamp (there's no `approval_submitted_at` column and M9 adds no
  migration). For a wizard run, creation → submission is usually a couple minutes,
  so it's a close approximation. Flagged; add a column if exactness matters.
- **The estimate reads the *actual* `enrich_with_metrics` (false for VAs), not the
  decorative "Metrics: On · locked" toggle** (§7.8 metrics enrichment is still
  unbuilt, an M7/M8 carry). So the estimate is honest about what runs; it just
  doesn't match the (cosmetic) toggle. Decide alongside §7.8.
- **The VA cost gate is largely latent at current rates + metrics-off:** with
  `enrich_with_metrics` false (the VA reality), even the most expensive
  non-recursive VA run (comprehensive, 10 silos, 2 deep-mined) estimates ~$4.80 —
  under the $5 cap. So in practice the cost-trigger fires only if the Owner lowers
  `va_soft_cap_usd` or once §7.8 metrics is built. This is the literal §8.4 intent
  ("most non-recursive runs pass; only recursive + unusually expensive require
  approval"), but it means the *recursive* trigger is the main intended gate — and
  that one isn't a VA UI control yet (above). `/expand` enforces the gate
  server-side regardless (a VA over-cap direct call → 403), so it's correct, just
  rarely hit. Flagged.
- **Owner-offline approval has the M8 chaining gap:** approve kicks `/expand`, but
  the expand → plan-articles chain is still **client-driven** (the wizard's
  ProgressStep). If the VA's browser is closed when the Owner approves, the run
  expands and parks at `awaiting_article_planning` until the VA reopens — and VAs
  have no session browser (M8) to find it again (the `/session/:id` route works if
  they have the URL). Server-side chaining + a VA resume surface are out of M9
  scope (explicitly). Flagged — the most likely thing to want next.
- **`recursive_fanout` is still not a VA wizard control** (§10.2: "not exposed…
  available only via explicit approval request"). The wizard's createSession sends
  `recursive_fanout: false`, so the wizard's approval trigger is purely cost > cap.
  `/fanout` stays owner-only (carried from M8 / RF). A VA-initiated recursive
  request path isn't wired — the cost-gate path is. Flagged as the literal §11.2
  "VA recursive → always approval" not being reachable from the VA UI yet.
- **`GET /workspace-settings` exists but the wizard reads the cap from the
  cost-estimate response** (which already carries `va_soft_cap_usd`), so the
  standalone endpoint is currently only used as documentation of the §11.4 read.
  Kept because the task called for it + it backs a future settings UI.

---

**M8 — VA wizard (PRD §15.1 / §10): complete & merged to `main` (2026-05-26, per
owner instruction).** Built on `claude/exciting-cannon-jTTVb` (this session's pinned
branch — *not* an `m8-…` branch, per the session task instruction), merged
`--no-ff` (remote `main` was at `d489f70`; the merge added the 3 M8 commits
cleanly). Backend 116 tests pass (98 prior + 18 new role tests), ruff clean, import
smoke OK; frontend builds strict-clean (tsc + vite). **Still not browser-validated**
(sandbox egress blocked, standing constraint) — validate on the deployed stack.

VA mode is a *configuration of the existing Owner UI*, not a parallel build (PRD
§15.1 rationale). The app is now **role-gated** in `App.tsx`: `me.role == "owner"`
→ the existing §9 Owner UI (unchanged); `va` → the §10 linear wizard + a restricted
results surface. A transient `/me` failure falls back to the *more-restricted* VA
routes (never exposes Owner views).

**Frontend (new `frontend/src/va/Wizard.tsx`):** the 9-step linear wizard (§10.1),
reusing the same `shared/api.ts` calls as the Owner creation flow. Steps: (1)
project pick (defaults to Scratch), (2) seed + collapsible audience/disambiguation
hints + soft English-only check, (3) run settings — **only** `topic_count` slider +
`coverage_mode` toggle, with metrics + relevance-threshold shown locked (folded into
the seed screen), (4) disambiguation **gated on `needs_disambiguation`** (skipped
otherwise), (5) silo review (remove/add/edit/audience-override; Continue disabled
< 3 silos), (6) deep-mine **capped at seed + 2** (extra checkboxes disable at the
cap), (7) cost confirmation **stubbed to "Run now"** (approval is M9), (8) progress
(polls `/summary`, **auto-chains** expand → plan-articles to keep the flow linear),
(9) results → routes to `/session/:id`. The **restricted results surface** reuses
the Owner views via a new `role` field on `SessionWorkspace`'s `SessionCtx`: VA
tabs = Table + Cluster + read-only Architecture (no Split). Cluster View for a VA =
rename + move-keyword only (no split/merge/delete/promote/edit-intent/H2/gap
accept-dismiss), plus a **stubbed "Request restructure from Owner"** per article.
Table bulk for a VA = Mark-covered + Move-to-cluster only (no Exclude/Restore).
Architecture View for a VA = read-only (no Generate/Regenerate; empty state says
the owner generates it).

**Backend (defense in depth, §10.3 / §11.2):** the service-role client bypasses
RLS, so VA capability limits can't lean on RLS — they're enforced in the API layer.
Added `get_role()` + a `require_owner` dependency (`app/auth/dependencies.py`).
Owner-only endpoints (403 for VA at the dependency layer, before any DB work):
cluster `delete` / `merge` / `split` / `promote-primary`, `coverage-gaps`
accept/dismiss, `POST /architecture`, `DELETE /sessions/{id}`, `/regate`,
`/cluster-preview`, `/routing-diagnostic`, `/lever3-simulate`, `/fanout`.
In-handler role checks: `/deep-mine` caps a VA at seed + `va_deep_mine_max_silos`
(=2) silos; `PATCH /clusters/{id}` lets a VA set only `name` (intent/H2s → 403);
bulk keyword `status` refuses `excluded` for a VA. New config knob
`va_deep_mine_max_silos: int = 2`. New tests: `tests/test_roles.py` (18) drive the
guards with an injected VA/owner + mocked storage.

**M8 decisions / divergences (flagged for review):**
- **Architecture stays owner-only** (`POST /architecture` → `require_owner`).
  §11.2 says VA architecture-regeneration is ✗ and the view is read-only, but the
  initial generation and a regenerate are the *same* endpoint, so I couldn't allow
  one without the other. Consequence: **a VA run ends at the article plan; the
  Architecture tab is owner-pending** (read-only empty state) until an owner
  generates it (the owner sees all sessions via RLS). The progress screen therefore
  shows expansion + planning stages only, not an Architecture stage. Conservative
  reading of §10.3; flagged.
- **`enrich_with_metrics` is shown "On · locked" in step 3 but does nothing** —
  metrics enrichment (§7.8) is still unbuilt (optional in v1), so Volume/KD/CPC stay
  "—". The session is still created with `enrich_with_metrics: false` (the wizard
  doesn't send a new field); the locked toggle is informational. Flagged — decide
  with §7.8.
- **"+ New project" (step 1) omitted** — there is no create-project endpoint
  anywhere in the build (the Owner browser can't create projects either; only the
  auto-Scratch exists). The wizard's project step is a picker over existing projects
  (Scratch by default). Flagged; needs a `POST /projects` if project creation is
  wanted (out of M8 scope).
- **Live cost estimate is a static band, not a real figure** (§7.2 #2 / §10.2 want
  a live cost). No cost-estimate endpoint exists (that's M9/M11); the wizard shows a
  rough `~$low–$high` band that updates with the silo count. Flagged.
- **English-only check (§10.2) is a soft, permissive warning** (flags non-Latin
  scripts via a Unicode-range regex; allows accents/punctuation; never hard-blocks).
- **"Request restructure from Owner" is a local stub** (an alert + "flagged"
  state) — the real owner notification / request record needs the M9 approval queue.
- **VA cost confirmation is the M9 stub** (always "Run now", no approval) — PRD
  §15.1 explicitly permits this during M8. `/fanout` is owner-only until M9 wires
  the approval-gated path for VAs.
- **No schema/migration in M8** — roles + `workspace_settings` already exist from
  M1; M8 is enforcement + UI only.
- **`plan-articles` `direct` mode is still reachable by a VA** (it's a planning-mode
  choice, not a capability-matrix restriction); the wizard never sends it, so VAs
  get orchestrator-planned articles (the settled default). Not gated — flagged as a
  judgement call.
- **Not browser-validated** — views compile strict-clean and the role guards have
  unit tests, but the live VA login → wizard → results round-trip (and that an owner
  vs. VA JWT actually resolves the right `role`) still needs checking on the
  deployed stack.

---

**M7 — Owner UI (PRD §15.1 / §9): complete & merged to `main` (2026-05-26).**
Built on `claude/sweet-ramanujan-PXvK0` (this session's pinned branch — *not* an
`m7-…` branch, per the session task instruction), merged `--no-ff`. Remote `main`
was at the M6 sign-off (`03c3e54`); the merge added the M7 commits cleanly
(`03c3e54..84f96b9`, no conflicts). **Live validation on the deployed stack is
still recommended** — merge happened per owner instruction, but sandbox egress
blocked browser testing (backend 98 tests + ruff clean, frontend builds
strict-clean). Split into two parts:

**M7a (read-only):** react-router added; the three views render against the
read-only M1–M6 API. **Table View** (§9.1) — sortable + filterable
(topic/cluster/source/length/question/text); Volume/KD/CPC show "—" (metrics
enrichment §7.8 is unbuilt/optional). **Cluster View** (§9.2) — article units
grouped by topic, gaps inline. **Architecture View** (§9.3) — two-panel site map +
linking matrix, regenerate; Send-to-Brief disabled (§16.2). **Split View** —
Table+Cluster side-by-side (desktop). **Project + Session Browser** (§9.4) —
left-rail projects, session list, click-to-resume (the UI session-resume that
calibration has worked around). New backend reads: `GET /projects/{id}/sessions`,
a `statuses` filter on `/keywords`, and `seed_keyword` on `GET /sessions/{id}`.

**M7b (editing):** all §9.2 cluster ops — rename, edit intent, edit H2s, promote
primary, move keyword, delete (→Unassigned, never destroyed), **merge**, **split**
(manual selection), accept/dismiss gaps, and an explicit **Re-run orchestrator**
(orchestrator stays the default — decision settled this session; `direct` remains
the opt-in flag, so no code flip). §9.1 Table bulk: exclude / mark-covered /
restore / move-to-cluster. §9.4 browser mutations: archive/unarchive, move
project, delete. New backend: `PATCH/DELETE /clusters/{id}`, `/promote-primary`,
`/clusters/merge`, `/clusters/{id}/split`, `/sessions/{id}/keywords/{status,move}`,
`/coverage-gaps/{id}/{accept,dismiss}`, `PATCH/DELETE /sessions/{id}`. Migration
`20260527000000_session_archive.sql` (adds `sessions.archived`) **applied live via
MCP**.

**M7 decisions / divergences (flagged for review):**
- **Membership-changing cluster edits (merge/split/delete/move) set
  `centroid_embedding = NULL`** rather than recomputing it. The centroid is only
  consumed by a *subsequent* re-plan's cross-topic dedup, which rebuilds every
  cluster anyway — so paying for an embedding call on each edit would be wasted,
  and NULL keeps edits deterministic + sandbox-testable (no OpenAI egress).
- **Per-topic orchestrator re-run is deferred;** only whole-session re-run is wired
  (the existing `/plan-articles`, which resets + rebuilds — the UI warns it
  discards manual edits). §9.2 lists both; per-topic needs a scoped pipeline path.
- **Split implements §9.2 option (a)** (manual keyword selection) only; option (b)
  (re-run orchestrator on the article at a stricter SERP threshold) is deferred.
- **Cluster filter in Table View is single-select** (315 clusters make chips
  impractical); topic/source are multi-select. PRD says multi for all — flagged.
- **Drag-and-drop keyword move not implemented** — used a per-keyword "move to…"
  select + Table bulk "move-to-cluster" instead (§9.2 explicitly allows the
  select-based alternative for mobile; covers the same operation).
- **`metrics enrichment` (§7.8) still unbuilt** → Volume/KD/CPC columns are "—".
  Optional in v1; decide before M8 whether to fold a minimal enrichment in.
- **Post-review fixes (adversarial pass, applied before merge):** (1) structural
  cluster edits (delete/merge/split/accept-gap) now call `delete_architecture()`
  (factored out of `reset_article_planning`) + the Cluster View invalidates the
  cached architecture query — they change the cluster-id set the stored
  `site_architecture` references, so leaving it would dangle (the same bug the M6
  post-review fix closed for re-plans). A regenerate rebuilds it. (2) `promote_primary`
  now verifies the keyword is a cluster member (ValueError → 400) and `split_cluster`
  restricts to keywords actually in the source + derives the new primary from those
  — previously an API caller could leave `clusters.primary_keyword_id` pointing at a
  foreign keyword (the UI never did this). (3) `accept_gap` is idempotent (a
  double-submit returns the existing placeholder, no duplicate).
- **Not browser-validated** — sandbox has no Supabase/Railway egress (standing
  constraint), so the views compile strict-clean (tsc) and the backend passes 98
  tests + ruff, but live rendering/edit round-trips still need checking on the
  deployed stack now that `main` carries the code.
- **Remaining LOW review items (not blocking, deferred):** cross-topic merge is
  allowed (endpoint checks same session, not same topic); `_require_cluster` does
  one redundant cluster read; no `max_length` on bulk id lists; `ArchitectureView`'s
  `busy`/effect are effectively dead (the workspace gate unmounts the view during a
  regen, correctness held by remount-refetch); excluded keywords stay visible in
  Table View (PRD §9.1 says hide); M7b business logic has only auth-gate tests (no
  DB in sandbox).
- **Out of scope (unchanged):** CSV export → M10; VA restrictions → M8;
  Brief-Generator handoff stays degraded-disabled; session **duplicate** (§9.4)
  deferred (ambiguous semantics — flagged).

---

**M6 — Site architecture (PRD §15.1 / §7.11): complete & signed off (2026-05-26).**
Built on `claude/gifted-clarke-pONCI`, merged `--no-ff`. **Validated live on
`retatrutide` `4ecefaa1`** (315 clusters, 5 silos): 5 pillars, 0 skipped, 315
supporting articles with **0 orphans / 0 bad parent refs**, 945 lateral article
links (3/article, **0 dangling**), all 10 pillar pairs cosine [0.77, 0.85] so the
>0.55 lateral rule holds — **all four §15.2 acceptance criteria pass**. First run
degraded 3/5 pillars to stubs (transient Anthropic rate-limit/overload under 5
parallel calls, *not* size-correlated); fixed by lowering `architect_max_workers`
5→2 + exponential backoff before the reprompt — re-run gave **0/5 degraded** with
strong titles (e.g. "How to Get Retatrutide: The Complete Guide to Access, Cost…"
/ `how to get retatrutide`). After article planning, each article-bearing silo
becomes a **pillar** (a high-level overview page that links down to its supporting
articles). New endpoints: `POST /sessions/{id}/
architecture` (async, 202 — poll `GET /summary`, whose payload now carries an
`architecture` block) and `GET /sessions/{id}/architecture` (read; 404 until
generated). One `site_architecture` row per session (`session_id` PK → a
re-generate upserts in place, satisfying §9.3's "Regenerate architecture").

**Design — LLM writes the prose, code wires the graph.** Opus 4.7 (reusing the
orchestrator's Anthropic client per §7.11) is called **once per pillar, in
parallel**, for the *editorial* fields only: title, target keyword, summary, 5–8
H2 outline. The **linking matrix is assembled deterministically** so the §15.2
acceptance rules hold by construction rather than on the model's good behavior:
(1) one pillar per accepted silo; (2) every supporting article up-links to its
pillar + every pillar down-links to all its articles; (3) no orphans (guaranteed
by the down-links); (4) pillars link laterally only where topic-embedding cosine
> 0.55. Lateral article links = 2–3 peers, prioritizing the orchestrator/dedup
`peer_article_links`, topped up by same-silo centroid nearest-neighbors. A
per-pillar LLM failure degrades that pillar to a deterministic stub (title = silo
name, outline = article names); all-degraded → session `error` (the architect is
down), mirroring the orchestrator.

**M6 decisions / divergences (flagged for review):**
- **Diverges from prompt B.3**, which has the model emit `supporting_article_ids`
  + all lateral links too. Made deterministic instead — same rationale as M5's
  deterministic cross-topic dedup (reproducible + testable; the acceptance rules
  can't be silently violated by a hallucinated link or a dropped article).
- **A silo with zero planned articles gets no pillar** (a childless overview page
  links down to nothing); such silos are listed in `architecture_json.skipped_
  silos`. Literal reading of §15.2 #1 ("one pillar per accepted silo") would force
  an empty pillar — conservative call, flagged.
- **`peer_article_links` from M5 are cross-topic** (set by dedup's loser→winner
  linking), not the within-silo links B.3 assumes the orchestrator set. The
  lateral-link assembly treats them as priority seeds, then fills within-silo by
  centroid — so cross-silo article links survive *and* the §7.11 same-silo 2–3
  target is met where peers exist.
- **Post-review fix (adversarial pass):** `reset_article_planning` now also
  deletes the session's `site_architecture` row. It's called by the plan/regate/
  fanout jobs, all of which delete + re-create clusters with fresh ids; without
  this, a re-plan left the stored architecture pointing at dead cluster ids (and
  `/summary` reported a stale graph as present). Architecture is downstream of the
  plan, so a re-plan now requires a fresh `/architecture` run.
- **Concurrency caveat (resolved):** ~5 simultaneous pillar calls burst Anthropic
  rate limits → most pillars degraded to stubs. `architect_max_workers` is now 2
  with exponential backoff + jitter before the reprompt (transport errors only;
  shape failures still reprompt immediately). Pillars are few, so throughput isn't
  the constraint. If a future seed has many more silos, revisit.
- Migration `20260526000000_site_architecture.sql` **applied to the live DB** (via
  Supabase MCP, 2026-05-26; table present, RLS on). Backend: 94 tests pass, ruff
  clean, import smoke OK; frontend builds.
- **Planner default still unresolved** (orchestrator default, direct via
  `{"direct": true}`) — carried in from RF, not touched by M6.

No Architecture View UI yet — that's M7 (§9.3, two-panel site map). M6 ships only
the read-only API (`api.ts` got `generateArchitecture` / `getArchitecture` +
types, matching how RF added `fanout()` without a view).

**Recursive Fanout (RF) — deepen each silo into sub-topics:** **complete**
(signed off 2026-05-26). PRD §7.7, Phase 1; spec in
`docs/recursive-fanout-spec.md`. A second stage on an already-expanded session:
`POST /sessions/{id}/fanout` takes each silo's top cluster representatives (from
the first pass's `statistical_clustering_log`) as **sub-anchors**, re-expands each
via the existing `run_expansion` (reused, with a new `include_seed_level=False`
to skip the bare-seed phrase endpoints that already ran), tags the new keywords
`recursive`, merges them into the stored pre-gate pool, and re-runs the unchanged
gate + Lever-3 routing + clustering. Depth hard-capped at 1 by construction.
Mining stays **off** at this level (M5 finding: mining adds gate-rejected noise).
Cost-gated: an unconfirmed `/fanout` returns the 5–8× estimate + sub-anchor plan
(HTTP 200, no spend); `confirm_cost: true` starts the run (202). Time budget
scales with sub-anchor count (`min(900, max(60, 25×count))`s) since RF does ~N×
the keyword work of a base expand. New code: `pipeline/recursive_fanout.py`,
`run_fanout_job` in `jobs.py`, `/fanout` in `api/sessions.py`, `fanout()` in
`frontend/src/shared/api.ts`. No schema change (Phase 1). Built on
`claude/pensive-ramanujan-vyJJD`; merged to `main`.

**RF validated live** on `retatrutide` session `4ecefaa1` (deployed stack,
console+MCP): expand → baseline `/plan-articles {direct}` → `/fanout {confirm_cost,
resolution 1.2}` → `/plan-articles {direct}`. Results: active pool 2,029 → 2,562,
of which **1,007 active keywords are recursive-sourced** (~39%); RF surfaced
18,045 recursive candidates, the gate kept ~6% (14,680 filtered_relevance, 2,358
junk) — healthy. **Zero off-niche peer leakage** (371 "peer" matches were all
legit `retatrutide vs <peer>` keywords naming the seed; true no-seed leaks = 0).
Articles 10 → 315.

**RF decisions / caveats (flagged):**
- **Article-count A/B is resolution-confounded.** The baseline plan ran on pass-1
  clustering at resolution **1.0**; the RF run re-clustered at **1.2**. So 10→315
  entangles "more keywords" with "finer clustering" — the clean RF signal is the
  keyword-level one (1,007 active recursive, 0 peer leak), not the 31× article
  number. The baseline's 10 articles (~200 kw/article) was itself an over-coarse
  anomaly. To isolate RF's article contribution, re-plan a non-RF session at res
  1.2 (cheap `/regate`, no DataForSEO) and compare to 315. **Not done.**
- **`recursive` provenance tag is best-effort:** it's per-(silo, keyword), so
  Lever-3 can route a keyword to a silo whose source list lacks the tag. Cosmetic
  (gating/clustering/counts unaffected); don't treat the tag count as exact.
- **Planner default unchanged** in this milestone — RF only touches the expand
  stage; the orchestrator-vs-direct global default is still open (see above).
- **Sub-anchors come from first-pass representatives** (owner's choice), so RF
  requires a prior `/expand`; `/fanout` 400s if there are no multi-keyword
  groupings to deepen.

M1 — Foundation: **complete** (signed off 2026-05-21). Built on `m1-foundation`.

M2 — Silo discovery + user review: **complete** (signed off 2026-05-23). Grounding
pass + demand sample + SERP-structure scrape + GPT-5.4 silo proposal; disambiguation
gate; silo review (remove/add/edit/override audience); finalize embeds silos into
`topics`. Validated against `retatrutide` (clean silos, zero peer-entity leakage)
and `mercury` (disambiguation gate fires). Built on `m2-silo-discovery`; M1+M2 then
merged to `main`, which is now the single deploy branch for Railway and Netlify.
Backend env reads `SUPABASE_SERVICE_KEY`/`SUPABASE_KEY` aliases (AR Tools naming).

M3 — Expansion pipeline: **complete** (signed off 2026-05-24). Per-silo DataForSEO
expansion + autocomplete + keyword persistence to `keywords` with source
attribution. Resolved a zero-yield bug: `keyword_suggestions` and `query_fanouts`
are phrase/seed-match endpoints that return near-zero on a silo-qualified anchor, so
they now run **once on the bare seed and fan out to every silo** (M4's relevance gate
sorts them per-silo); `keyword_ideas` and PAA keep their per-silo broad anchor.
Temporary `/debug/dataforseo` probe removed after tuning. Built on
`claude/blissful-cray-Hm9tY`; merged to `main`.

M4 — Competitor mining + relevance gate + clustering: **complete** (signed off
2026-05-24). Deep-mine selection (§7.2, `POST /sessions/{id}/deep-mine`); SERP
competitor mining on gated silos + the always-mined seed fanned to all silos
(§7.4); relevance gate with junk filter + cross-silo embedding dedup, tagging
`active`/`filtered_relevance`/`filtered_junk` and writing `relevance_score` (§7.6);
per-silo Louvain clustering with medoid representatives, persisted to
`statistical_clustering_log` (§7.9). `/expand` runs the full pipeline behind an
atomic run guard (409 if already running); clustering memory bounded (float32 +
`clustering_max_nodes=2500`). Verified live on `retatrutide` (one gated silo:
3,953 competitor kw, 1,341 active / 8,522 filtered_relevance / 43 junk, 4 groupings
@ cohesion 0.784). `autocomplete_max` lowered 1500→500 (autocomplete is the
noisiest/slowest source; the gate discards most of it). Built on
`m4-competitor-clustering`; merged to `main`.

**M4 carried-forward (accepted, not blocking):**
- **Synchronous 5-min wall (→ M11):** the whole pipeline runs in one request; large
  runs exceed Railway's 5-min edge cap. The backend completes and persists anyway
  (sync `def` → threadpool, not cancelled on client disconnect), but the UI may
  error and there's no session-resume until M7. Internal per-stage 240s budgets are
  a safety valve to return before the cap; they truncate the lowest-yield tail
  (mostly autocomplete) and surface a "partial mining" banner. **Real fix = async +
  polling, deferred to M11** (confirm M11's scope folds this in — PRD §15.1 M11 is
  literally "cost + observability").
- **Hygiene leftovers (low):** dead `insert_keywords` in `storage/silo.py` (#7);
  no unfinalized-run guard on `/expand` (#10, gracefully degrades); duplicate
  `ranked_keywords` calls when two gated silos share a domain (#12).
- **Tuning notes (later/calibration):** clustering yields few large communities
  (4 groupings, edge threshold 0.55) — raise the threshold / Louvain resolution if
  M5 wants finer granularity; relevance threshold 0.62 filters hard on a single
  broad silo (~10–14% retained).
- **Stuck-running edge:** a hard crash / deploy mid-run leaves status `running`, so
  re-running that session 409s; recovery is to start a new session (no resume yet).

M5 — Article planning orchestrator + cross-topic dedup: **complete** (signed off
2026-05-25). Core §7.10 shipped: per-silo editorial orchestrator (Claude Opus 4.7,
forced tool-use / strict schema), SERP fetch per candidate primary, deterministic
cross-topic dedup, `clusters` + `coverage_gaps` tables (real RLS), staged
persistence across the clusters↔keywords FK cycle. Built on
`claude/youthful-bohr-8MovM`; merged to `main` (single deploy branch).

M5 grew well beyond §7.10 while validating live on `retatrutide` (session
`ea83f985`). What else shipped under M5:
- **Async pipeline + status polling (pulled forward from M11).** `/expand`,
  `/plan-articles`, `/regate` claim the run, submit to a background worker, return
  202; frontend polls `GET /sessions/{id}/summary`. Kills the 5-min edge wall.
  `app/jobs.py`; `sessions.last_error`.
- **Chunked orchestrator.** One Opus call per silo overran token/timeout at 200+
  groupings; now planned in parallel chunks of `orchestrator_groupings_per_call`
  (12). A chunk degrades alone; all-silos-degraded → error.
- **Generic peer-entity filter (beyond §7.6, which left brand detection out).**
  Grounding (GPT-5.4) emits per-seed `aliases` + `peer_entities` (stored on the
  session); the gate drops a keyword that names a peer but not the seed/alias.
  Seed-agnostic — works for any subject (drug/product/place). Killed ~2,100
  tirzepatide/ozempic/generic-trials keywords on the test seed.
- **Lever 3 — single-silo routing at the gate** (`relevance_assign_best_silo`,
  default on). Each keyword goes to its one best silo (argmax raw cosine to the
  rationale anchor — empirically the best of four candidate signals, per the
  routing diagnostic), instead of staying active in every silo. Eliminates the
  cross-silo fanout duplication at source (active == distinct active).
- **Direct mode** (`POST /plan-articles {"direct": true}`): groupings → articles
  with no LLM (representative = primary, rest = supporting; singletons included),
  then dedup. Fast/cheap/deterministic, max article count.
- **Calibration tooling (read-only, no DataForSEO):** `/regate` (re-gate the
  stored pool at new threshold/granularity), `/cluster-preview` (resolution
  sweep), `/routing-diagnostic` (compare silo-anchor signals), `/lever3-simulate`.
- Relevance threshold default 0.62 → **0.52**; Louvain `resolution` exposed.
- Migrations added: `clusters`, `session_last_error`, `peer_entities`.

**M5 decisions / divergences (flagged for review):**
- **Direct mode diverges from §7.10**, which mandates the orchestrator as the core
  step. The orchestrator remains the default and is fully built; direct mode is an
  opt-in flag chosen for article *volume* (orchestrator consolidates, which fights
  a couple-hundred-article goal). Owner is aware and chose direct for now.
- **Cross-topic dedup is deterministic** (cosine > 0.85 OR top-3 SERP overlap ≥
  2/3, winner = higher own-silo relevance), not the "single LLM call" §7.10.4 also
  describes. Reproducible + testable; revisit if editorial dedup is wanted.
- **Centering (common-mode removal) for routing was tried and reverted** —
  measured worse; raw rationale-anchor cosine is the routing signal.

**M5 findings that shape RF (the next milestone):**
- Deep-mining *more* silos (§7.2) adds raw competitor keywords but the relevance
  gate filters most as off-niche, so the *useful* pool barely grows (~900 active).
  Mining is not the lever for more genuine articles.
- Embedding-based silo routing is ~71% accurate and weakly discriminative
  (everything ≈ "retatrutide"); good enough but not great.
- **Recursive fanout (§7.7) is the right lever for article volume/depth** — it
  generates genuinely on-niche sub-topic keywords per silo, unlike competitor
  mining. Hence RF is next.

**Open / carried-forward into RF and beyond:**
- The orchestrator-vs-direct default is unresolved (currently orchestrator default,
  direct via flag). Decide during RF whether direct becomes default.
- Routing distribution can skew (clinical-trials, or mechanism after re-mining) —
  a routing-quality refinement is deferred.
- Session resume in the UI is still M7 (calibration runs are driven via the
  console against the deployed API; the UI can't reopen a session).
- Test session `ea83f985` has a misspelled seed (`retratrutide`); the correct
  spelling was supplied via the alias override. Not a code issue.

---

## Version history of this file

| Version | Date | Notes |
|---|---|---|
| 1.0 | 2026-05-20 | Initial CLAUDE.md created as part of M1 kickoff. Locks architectural decisions from PRD v1.7. |
| 1.1 | 2026-05-25 | M5 signed off (orchestrator + dedup, plus async execution, peer-entity filter, Lever-3 routing, direct mode, calibration tooling). Recursive Fanout (§7.7) re-sequenced as the next milestone ahead of the PRD's M6; spec in `docs/recursive-fanout-spec.md`. |
| 1.2 | 2026-05-26 | Recursive Fanout (§7.7, Phase 1) signed off — `/fanout` second-stage that re-expands each silo's top cluster representatives as sub-anchors, cost-gated, re-gate/re-cluster on the enlarged pool. Validated live on `retatrutide` (`4ecefaa1`): 1,007 active recursive keywords, 0 peer leak. Build returns to the PRD sequence; **M6 (site architecture) is next.** |
| 1.3 | 2026-05-26 | M6 (§7.11 site architecture) **implemented, pending review** — `POST/GET /sessions/{id}/architecture`, `site_architecture` table (one row/session, upsert on regenerate), pillar editorial content via Opus (per-pillar, parallel) + deterministic linking matrix guaranteeing the §15.2 acceptance rules. Migration applied to the live DB (via MCP); no live validation yet (sandbox egress). Built on `claude/gifted-clarke-pONCI`. |
| 1.4 | 2026-05-26 | M6 **signed off** — validated live on `retatrutide` `4ecefaa1` (315 clusters): 5 pillars, 0 orphans, 0 dangling links, all four §15.2 criteria pass. Fixed transient rate-limit degradation (`architect_max_workers` 5→2 + backoff). Merged to `main`. **M7 (Owner UI) is next.** |
| 1.5 | 2026-05-26 | M7 (Owner UI, §9) **implemented, pending review + live validation.** M7a: react-router + read-only Table/Cluster/Architecture/Split views + Project+Session Browser (UI session-resume); new reads `GET /projects/{id}/sessions`, `statuses` keyword filter, `seed_keyword` on `GET /sessions/{id}`. M7b: full cluster editing (rename/intent/H2/promote/move/delete/merge/split), gap accept/dismiss, whole-session orchestrator re-run, Table bulk actions, browser archive/move/delete; migration `20260527000000_session_archive.sql` applied live via MCP. Orchestrator-vs-direct default **settled: orchestrator stays default** (no code flip). Built on `claude/sweet-ramanujan-PXvK0`; 98 backend tests pass, frontend builds; not browser-validated (sandbox egress). Deferred/flagged: per-topic re-run, split option (b), session duplicate, metrics enrichment (§7.8). |
| 1.6 | 2026-05-26 | M7 **merged to `main`** (`--no-ff`, per owner instruction) after an adversarial review pass + fixes: structural cluster edits now invalidate the stored `site_architecture` (was left dangling); `promote_primary`/`split_cluster` guard against a primary pointing at a non-member keyword (→ 400); `accept_gap` is idempotent. Remote `main` was at the M6 sign-off (`03c3e54`); the merge added only the M7 commits (`03c3e54..84f96b9`, no conflicts). Live validation on the deployed stack still recommended. **M8 (VA wizard, §10) is next.** |
| 1.7 | 2026-05-26 | M8 (VA wizard, §10) **complete & merged to `main`** (per owner instruction; still pending live validation). Role-gated app (`App.tsx`): owner → §9 Owner UI (unchanged); VA → new `frontend/src/va/Wizard.tsx` 9-step linear wizard (step-gated: disambiguation only when ambiguous; settings locked to topic_count + coverage_mode; deep-mine capped at seed + 2; cost confirmation stubbed to "Run now") + a restricted results surface (Table/Cluster/read-only Architecture via a new `role` on `SessionCtx`; no Split/merge/delete/promote/gap/exclude; "Request restructure" stub). Server-side enforcement (defense in depth, §10.3/§11.2): new `require_owner` dep + `get_role()` gate cluster delete/merge/split/promote-primary, gap accept/dismiss, `/architecture`, session delete, `/regate`, `/cluster-preview`, `/routing-diagnostic`, `/lever3-simulate`, `/fanout`; in-handler checks for the deep-mine cap (`va_deep_mine_max_silos=2`), VA rename-only `PATCH /clusters`, and VA no-exclude bulk status. Built on `claude/exciting-cannon-jTTVb`, merged `--no-ff` to `main`; 116 backend tests (18 new in `tests/test_roles.py`) + ruff clean, frontend builds; not browser-validated. Flagged: architecture stays owner-only (so a VA run ends at the article plan; Architecture tab is owner-pending), metrics toggle is decorative (§7.8 unbuilt), no "+ New project" (no endpoint), static cost band. **M9 (approval workflow, §11.3) is next.** |
| 1.8 | 2026-05-26 | M9 (approval workflow, §11.3) **complete & merged to `main`** (per owner instruction; merged `--no-ff`, remote `main` was at `27f5731`, conflict-free; still pending live validation). No schema/migration (all approval columns + the `pending_approval`/`rejected` statuses exist from M1). New pure cost model `backend/app/cost.py` (§8.1-derived; standard/comprehensive+metrics stay under the $5 VA cap, oversized + recursive runs exceed it). Gate placed at the cost-bearing `/expand` (the conservative read of §11.3's whole-run framing, since silo discovery already runs at `POST /sessions`). New endpoints: `GET /workspace-settings`, `GET /sessions/{id}/cost-estimate`, `POST /sessions/{id}/submit-for-approval` + `/cancel-approval` (VA), `GET /approvals` + `POST /sessions/{id}/approve` + `/reject` (owner-only); `/summary` gained an `approval` block. Frontend: wizard CostStep fetches the real estimate + branches Run-now vs Submit-for-approval → new WaitingStep (30s poll, cancel, adjust-&-resubmit on reject); Owner Approvals page (`/approvals`) + decision modal; AppShell owner-only Approvals nav badge. Built on `claude/jolly-heisenberg-Z06PH`; 139 backend tests (9 cost + 14 approvals new) + ruff clean, frontend builds; not browser-validated. Flagged: gate at `/expand`; reject reuses the same session (no clone); queue "submitted at" = `created_at`; estimate reads actual (false) metrics flag; owner-offline approval keeps M8's client-driven expand→plan chain; `recursive_fanout` still not a VA wizard control. **M10 (CSV export, §12) is next.** |
| 1.9 | 2026-05-28 | M10 (CSV export, §12) **complete & merged to `main`** (per owner instruction; merged `--no-ff`, remote `main` was at the M9 merge `1e0db30`, conflict-free; still pending live validation; built on `claude/wonderful-allen-oTKaO`). Three formats from current Postgres state via **pure, unit-tested** builders (`backend/app/csv_export.py`): flat (one row/keyword, §9.1 columns, Volume/KD/CPC blank), topic_grouped (one CSV/topic delivered as a single `.zip`), architecture (one row/page — pillar or supporting article — name-resolved links; 400 if no architecture). Backend uploads snapshots to the new private **`csv-snapshots`** Storage bucket under `{user_id}/{session_id}/{ts}-{rand8}.{ext}` via the service client and serves a **time-limited signed URL** (`csv_signed_url_ttl_s`=3600); re-download re-signs fresh. New router `backend/app/api/exports.py`: `POST /sessions/{id}/export?format=…` (sync, both roles, RLS-scoped), `GET /sessions/{id}/exports`, `GET /exports/{id}/download`. Migration `20260528000000_csv_exports.sql` (`fanout.csv_exports` + real RLS via a sessions-join) **applied live via MCP**; the private bucket **created via MCP**. Frontend: new **Exports tab** (`owner/views/ExportsView.tsx`) on both Owner + VA workspaces; `shared/api.ts` `createExport`/`listExports`/`downloadExport`. 165 backend tests (14 csv-builder + 12 export-API new) + ruff clean; frontend builds strict-clean. **CSV formula-injection hardening** on every text cell; signed URLs carry a server-side `Content-Disposition` attachment name; a failed export removes its orphan Storage object. **Storage upload / signed URLs / live download round-trip NOT sandbox-validated — deploy-only.** Flagged: sync generation; flat/topic_grouped use the surviving pool (active/excluded/covered); topic_grouped = one zip; "export selected" (§9.1) deferred. **M11 (cost + observability) is next.** |
| 1.10 | 2026-05-29 | M11 (cost + observability, §16) **complete, pending review + live validation** — the final milestone; M1–M11 now all built. Real-metered per-step cost attribution: a `CostMeter` (`app/cost_meter.py`) accumulates DataForSEO's real per-call charge + token-derived LLM cost, flushed live to `sessions.actual_cost_usd` + a new `cost_breakdown` jsonb every 10s from the background jobs (`app/cost_attribution.py`), cumulative across a session's runs. A `ContextThreadPoolExecutor` (`app/concurrency.py`) propagates the meter + `session_id`/`correlation_id` into the pipeline's nested API-call threads (also closing a latent §16.3 logging gap). The four external-call sites now populate the `cost_usd` log field. `GET /summary` carries a live `cost` block → a `CostBanner` on the Owner workspace + VA progress screen (§8.4). Owner-only `GET /sessions/{id}/debug` (require_owner) + `owner/DebugView.tsx` expose `statistical_clustering_log` + `orchestrator_log` + cost (§15.3 #8). Migration `20260529000000_session_cost_breakdown.sql` applied live via MCP. Built on `claude/exciting-davinci-tZGwH` (off `main` `4b10ed2`); 176 backend tests (11 new) + ruff clean, frontend builds. **Not sandbox-validated** (egress). Flagged: LLM $/token rates are estimates (DataForSEO cost is real); breakdown keyed by pipeline phase not §8.1 line item; cost cumulative across re-runs; §7.8 metrics still unbuilt so §15.3 #7 "+metrics" can't be exercised. Active milestone → v1 MVP feature-complete; remaining = the §15.3 live-validation checklist. |
| 1.11 | 2026-06-11 | Synced this file with `handoff.md` (which had moved ahead of it): M11 **merged to `main` + deployed**, meter confirmed working in prod; Opus meter rate recalibrated (15, 75) → (5, 25) USD/1M tok; `estimated_cost_usd` now persisted on every run path; **§7.8 metrics enrichment BUILT** (`keyword_metrics`, shipped 2026-05-29) — prior “unbuilt” flags in this file are stale; writer-ownership refactor (orchestrator no longer emits `suggested_h2s`; **site architecture now fully deterministic / LLM-free** — per-pillar Opus call removed, writer module owns pillar editorial + all H2s; PRD §7.10/§7.11 divergence, owner decision); internal links capped at ≤5/page with a cycle-based no-orphan guarantee + a runtime `link_health()` audit (live-verified on session `790f750f`); all 14 `fanout` migrations confirmed applied to prod (lesson: applying a new migration via Supabase MCP is part of the deploy). Locked-decisions table updated (architecture LLM-free; writer model = Sonnet 4.6 per handoff §9.11); `handoff.md` added to Key file locations as the authoritative live log. Remaining: finish the handoff §2 live-validation checklist; **M12 (Writer foundation) is design-locked (handoff §9.11) but blocked on the §9.13 Blog Writer PRD artifact fetch** (owner running it in a separate chat, 2026-06-10); address the §8.7 `sie_cache` RLS finding before M12 ships. Also fixed the 1.9/1.10 row ordering in this table. |
| 1.12 | 2026-06-15 | **Consolidated the two divergent Blog-Writer planning branches** (`claude/peaceful-mayer-iho6m4` + `claude/wizardly-clarke-3zxvh4`) onto `claude/focused-wright-kj3gyr` — the planning had been scattered across two unmerged branches with a duplicated bundle and contradictory milestone numbering. Adopts the **post-v1 content-generation re-sequence** (owner decisions 2026-06-12, introduced on `peaceful-mayer` but never versioned here): **M12 = SIE** (ScrapeOwl + TextRazor, write-time/lazy) → **M13 = Brief Generator** (v2.3, all-DataForSEO sources) → **M14 = Writer** (`1.7-no-context` degraded) → **M15 = scheduling + link injection** — superseding the older "M12 = Writer" framing. New planning docs landed: `docs/blog-writer-pipeline-bundle.md` (the 8-PRD bundle, verbatim), `docs/blog-writer-live-contract.md` (prod I/O ground truth), `docs/sie-module-plan.md`, `docs/brief-generator-module-plan.md`, `docs/writer-module-plan.md`. Reconciliations made during the merge: **deduped the bundle** (both branches added byte-identical copies under different names — kept `pipeline-bundle.md`, the name the module plans cite by line-range); **collapsed two redundant §9.13 "resolved" boxes** into one; **corrected the §9.11 Writer model tier** to MIXED **Sonnet 4.6** (prose) + **Haiku 4.5** (title/CTA/ICP-judge) per §17 (was "all-Sonnet"); folded in the live-contract corrections (brief runs **v2.6** in prod vs v2.3 in the PRD; real schema cols `module`/`input_payload`/`output_payload`; writer `article` = Markdown section array; **not** adopting the Eng-Spec 2-service topology). **Docs-only — no code.** Both source branches remain on `origin` for provenance. |
| 1.13 | 2026-06-15 | **Embeddings provider swap (locked-decision override, owner): OpenAI `text-embedding-3-small` → Google `gemini-embedding-001` @ 1536-dim (Matryoshka), whole-app, quality/consistency.** **Slice 1 (code, shipped DORMANT):** new provider-pluggable embedder `backend/app/llm/embeddings.py` (`OpenAIEmbedder` + `GeminiEmbedder` — REST `:batchEmbedContents` via httpx, `outputDimensionality=1536` + L2-normalize for truncated vectors + 100/request chunking); `OpenAILLM.embed` delegates to the backend (the `LLMError` contract preserved for callers); `get_llm()` builds the Gemini backend when `embedding_provider=gemini`; config adds `embedding_provider`/`gemini_api_key`/`gemini_embedding_model`/`gemini_embedding_dim`/`gemini_embedding_task_type`; cost-meter rate (`gemini-embedding-001` $0.15/1M, tokens estimated from input length). **Default `embedding_provider=openai` → prod untouched until cutover.** All embeddings flow through the single `get_llm().embed` seam (verified). `tests/test_embeddings.py` added; ruff + py_compile clean + logic validated in isolation; full pytest not sandbox-runnable (deps absent — validate in CI/deployed). 1536-dim truncation keeps the `vector(1536)` schema (no migration). Brief Gen §7.3's 3-large exception is **superseded** by this. **Slice 2 (freeze-old-sessions guard) shipped 2026-06-15:** migration `20260615000000_session_embedding_model.sql` tags `sessions.embedding_model` (existing rows backfill to `text-embedding-3-small`); `active_embedding_model()` helper; `create_session` tags new sessions; a 409 guard `_assert_embedding_current` on `/expand` `/regate` `/fanout` `/plan-articles` `/architecture` refuses a session whose tag ≠ the active model (a no-op while dormant, since active == OpenAI). Also: `GeminiEmbedder` sends the key as the `x-goog-api-key` header (not a URL param) + owner-only `GET /debug/embedding-health` probe. **Remaining ops to cut over: `GEMINI_API_KEY` ✅ provisioned; apply the migration to prod (Supabase MCP); set `EMBEDDING_PROVIDER=gemini` + redeploy; smoke-test via `/debug/embedding-health`; recalibrate the 8 cosine thresholds on live Gemini runs.** |
