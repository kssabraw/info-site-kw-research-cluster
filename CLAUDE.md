# CLAUDE.md

This file is read automatically by Claude Code at the start of every session. It contains the persistent context, locked decisions, and rules that apply to **every** milestone in this build. Read it first, then the PRD.

---

## What this project is

The **Topic Fanout Tool** is a keyword research and niche-site architecture planning app. Given a single seed keyword, it produces a complete content map for a niche authority site: silos (top-level subfolders), articles within each silo with target keywords and H2 outlines, and an internal linking structure.

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
| LLM (orchestrator + architecture) | Anthropic `claude-opus-4-7` with tool-use mode for strict-schema JSON |
| Embeddings | OpenAI `text-embedding-3-small` |
| External data | DataForSEO (Labs + SERP + Keyword Data) |
| Clustering | NetworkX + python-louvain |

API keys (DataForSEO, OpenAI, Anthropic, Supabase) are already configured at the Railway project level and inherited by this service. No new keys need provisioning.

---

## Milestone discipline

The build is sequenced into 11 milestones (M1–M11) defined in PRD §15.1. **Build one milestone at a time.** After each, stop and wait for human review before starting the next.

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

**M7 — Owner UI (PRD §15.1 / §9): implemented, pending review + live validation.**
Built on `claude/sweet-ramanujan-PXvK0` (this session's pinned branch — *not* an
`m7-…` branch, per the session task instruction; not yet merged to `main`). Split
into two sign-off gates:

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
- **Not browser-validated** — sandbox has no Supabase/Railway egress (standing
  constraint), so the views compile strict-clean (tsc) and the backend passes 98
  tests + ruff, but live rendering/edit round-trips need checking on the deployed
  stack (the M7a/M7b branch must deploy, or merge to `main`, first).
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
