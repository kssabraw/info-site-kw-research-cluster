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

**M5 — Article planning orchestrator + cross-topic dedup** (next; awaiting kickoff)

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

M5 Done state (per PRD §15.1 / §7.10): SERP fetches for candidate primary keywords;
per-silo editorial orchestrator (Claude Opus 4.7, tool-use/strict-schema) converts
statistical groupings into article plans (merge/split/promote-demote/route/drop);
cross-topic dedup pass; `clusters` table populated with article-level records;
coverage gaps persist to `coverage_gaps`.

When M5 is complete and approved, update this section to reflect M6 as the active milestone.

---

## Version history of this file

| Version | Date | Notes |
|---|---|---|
| 1.0 | 2026-05-20 | Initial CLAUDE.md created as part of M1 kickoff. Locks architectural decisions from PRD v1.7. |
