# Handoff — Topic Fanout Tool build

This is a session-continuity doc. **Read `CLAUDE.md` and `docs/topic-fanout-prd-v1_7.md` first** — they hold the locked decisions and the spec. This file captures live state, the immediate next action, and hard-won gotchas not in those docs.

_Last updated: 2026-05-24. Current `main` HEAD: `1ac3cbf`._

---

## 1. Where the build is

- **M1 — Foundation:** ✅ complete & signed off. Auth, roles, `projects`/`sessions`/`workspace_settings`/`user_profiles` under the `fanout` schema with RLS; FastAPI `/healthz` + `/me` + `/projects`; React login + project list.
- **M2 — Silo discovery + review:** ✅ complete & signed off. Validated on `retatrutide` (clean silos, zero peer-entity leakage) and `mercury` (disambiguation gate fires).
- **M3 — Expansion pipeline:** ✅ complete & signed off (2026-05-24). Per-silo expansion + autocomplete + keyword persistence with source attribution. `keyword_suggestions`/`query_fanouts` run once on the bare seed, fanned to all silos.
- **M4 — Competitor mining + relevance gate + clustering:** ✅ complete & signed off (2026-05-24). Deep-mine selection (§7.2), SERP competitor mining on gated silos + always-mined seed (§7.4), relevance gate w/ junk filter + cross-silo embedding dedup (§7.6), per-silo Louvain clustering → `statistical_clustering_log` (§7.9). Verified live on `retatrutide` (1 gated silo: 3,953 competitor kw, 1,341 active, 4 groupings @ cohesion 0.784). `autocomplete_max` lowered 1500→500. Built on `m4-competitor-clustering`; merged to `main`.
- **M5+ — not started.** M5 = article planning orchestrator + cross-topic dedup (PRD §15.1, §7.10).

## 2. Immediate next action (resume here)

**M4 is done. Next is M5 — do not start it without a human go-ahead** (milestone discipline: stop for review between milestones). When kicking off M5, read PRD §7.10 (editorial orchestrator: merge/split/promote-demote/route/drop), §7.10.1–.2 (inputs/decisions), the cross-topic dedup pass, and the `clusters` + `coverage_gaps` schema in §13. The orchestrator is **Claude Opus 4.7** in tool-use/strict-schema mode (per locked decisions), run once per silo, consuming each silo's groupings from `statistical_clustering_log` + a SERP fetch per candidate primary keyword.

**Before M5, decide on #1 (the 5-min wall).** M4 runs the full pipeline synchronously; M5 adds per-candidate SERP fetches + an LLM call per silo, making the synchronous request even longer. The human chose to defer the async fix to **M11** and accept that large runs error in the UI while completing server-side (verify via Supabase). If M5's added latency makes that untenable, revisit (see §4).

## 3. Deploy & infra state (CRITICAL — caused most of the pain this session)

- **`main` is the single deploy branch** for both Railway and Netlify. Milestones are built on `m{N}-...` branches and **merged to `main` (`--no-ff`)** when validated. Do NOT expect deploys from feature branches.
- **Railway** service `info-site-kw-research-cluster` (project `AR Tools`): **Root Directory = `backend`**, Dockerfile build, deploy branch `main`. `railway.json` has no `startCommand` (Dockerfile CMD owns port binding). `/healthz` returns the running commit via `RAILWAY_GIT_COMMIT_SHA`.
- **Netlify** site `kw-research-module` (id `dc24cc19-d745-4074-8967-e037f3c5e86a`): base dir `frontend/`, production branch `main`. Env vars set: `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.
- **Supabase** project = **AR-Internal-Tools**, ref **`wvcthtmmcmhkybcesirb`**, URL `https://wvcthtmmcmhkybcesirb.supabase.co`. Accessible via the Supabase MCP tools (apply_migration / execute_sql / get_logs). The `fanout` schema is **exposed in PostgREST** (Settings → API → Exposed schemas) — required, was a manual step.
- **Env var naming gotcha:** Railway provides the keys as **`SUPABASE_SERVICE_KEY`** and **`SUPABASE_KEY`** (AR Tools convention), NOT `SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_ANON_KEY`. `app/config.py` uses `AliasChoices` to accept both. Don't rename the shared Railway vars.
- **Sandbox can't reach** Supabase / Railway / OpenAI / DataForSEO (egress allowlist). PyPI, npm, GitHub API work. So **all live integration validation happens on the deployed stack**, and Supabase introspection happens via the MCP tools (which run server-side).

## 4. Known issues / open items

- **The 5-min synchronous wall (BIGGEST open item → M11).** The whole pipeline (`/expand`) runs in one HTTP request. **Railway's edge caps requests at 5 minutes (confirmed not configurable).** A large run exceeds it; the browser errors, but the backend keeps running (sync `def` → threadpool, not cancelled on client disconnect), completes, and persists — so data isn't lost, but the UI never sees it, and there's no session-resume until M7 (verify via Supabase instead). Internal per-stage budgets (`EXPANSION_TIME_BUDGET_S` / `COMPETITOR_TIME_BUDGET_S`, 240s each) are a safety valve to return *before* the edge cap; hitting one truncates the lowest-yield tail (mostly autocomplete) and shows a "partial mining" banner. **Real fix = async + polling, deferred to M11** — but note PRD §15.1 M11 is literally "cost + observability", so confirm the async work has an explicit home there. Mitigation knobs now: `AUTOCOMPLETE_MAX` (already 500), `EXPANSION_MAX_WORKERS`/`COMPETITOR_MAX_WORKERS` (raise to finish faster).
- **M4 ranked_keywords is domain-level, not URL-level.** §7.4 says "per URL ranks 1–20"; DataForSEO's `ranked_keywords` target is a domain, so we dedupe the top URLs to domains and filter rank ≤ 20 server-side. Verified live (3,953 competitor kw on one silo). The filter path (`ranked_serp_element.serp_item.rank_absolute`) is the documented shape; if it's ever wrong the failure is quiet (mining degrades to 0 + degraded notes, no crash).
- **M4 hygiene leftovers (low, not fixed):** dead `insert_keywords` in `storage/silo.py` (replaced by `insert_classified_keywords`); `/expand` has no guard against running before `/finalize` (degrades gracefully — all active, no scoring); two gated silos sharing a domain make duplicate `ranked_keywords` calls (minor cost).
- **M4 stuck-running edge:** the `/expand` run guard (atomic `try_mark_running`) 409s if status is already `running`. A hard crash / deploy mid-run leaves status stuck `running`, so re-running *that* session 409s forever — recover by starting a new session (no resume until M7).
- **Tuning notes (calibration):** clustering yields few large communities (4 groupings, edge threshold 0.55) — raise the edge threshold / Louvain resolution if M5's orchestrator wants finer input; relevance threshold 0.62 filters hard on a single broad silo (~10–14% retained). PAA tier-1 still returns 0 on silos whose broad anchor isn't a natural Google query (smallest contributor; left as-is).
- **`gpt-5.4` + `web_search`** (silo discovery) work in prod but were never verifiable from the sandbox; `OPENAI_SILO_MODEL` / `OPENAI_WEB_SEARCH_TOOL` env vars allow correction without a code change.
- **Session resume in the UI:** the data persists at every step, but the frontend can't reopen a session — **deferred to M7** (Project + Session Browser, §9.4).
- **`status: complete`** is set at the end of the M4 pipeline as the "current pipeline terminus"; M5 must move this downstream.

## 5. Architecture quick map (backend `backend/app/`)

- `main.py` — FastAPI app, CORS, correlation-id middleware, routers.
- `config.py` — `Settings` (pydantic-settings); env aliases; expansion knobs.
- `api/` — `health.py`, `projects.py`, `sessions.py` (silo discovery + `/deep-mine` + `/expand` full-pipeline endpoints).
- `auth/dependencies.py` — `require_user` (verifies Supabase JWT via service client; logs real reason on failure).
- `storage/supabase_client.py` — service client (RLS-bypass, admin writes) + user client (anon key + user JWT, RLS-enforced reads). `storage/silo.py` — session/topic/keyword DB ops incl. `set_topics_gating`, `get_topic_embeddings`, `insert_classified_keywords`, `try_mark_running`.
- `llm/openai_client.py` — GPT-5.4 grounding + silo proposal (Responses API + web_search) + `embed()`.
- `dataforseo/client.py` — DataForSEO calls (demand sample, SERP structure, expansion endpoints, autocomplete; M4: `serp_top_urls`, `ranked_keywords`, `domain_of`).
- `pipeline/` — `silo_discovery.py` (M2), `expansion.py` (M3), `competitor.py`/`relevance.py`/`clustering.py` (M4), `orchestrate.py` (M4 `run_refinement_pipeline` = expansion→mining→gate→clustering), `models.py`.

Frontend: `frontend/src/owner/SiloDiscovery.tsx` is the whole flow (seed → disambiguation → silo review → finalize → **deep-mine selection** → run pipeline → results). `shared/api.ts`, `shared/auth.tsx`, TanStack Query. Progress UI = `WorkingProgress` (discovery ~20–40s; pipeline ~3–6 min estimate).

Schema migrations in `supabase/migrations/`: `..._fanout_initial.sql` (M1), `..._topics.sql` (M2), `..._keywords.sql` (M3), `..._keywords_relevance.sql` (M4: `keywords.relevance_score`). All applied to the live DB.

## 6. Useful commands / queries

Backend (from `backend/`, venv at `.venv`):
```bash
. .venv/bin/activate
python -m pytest -q          # 55 tests, all passing
ruff check app/ tests/
python -c "import app.main"   # import smoke test
```
Frontend (from `frontend/`): `npm run build` (tsc + vite).

Per-silo / per-source breakdown for the latest run (run via Supabase MCP `execute_sql`, project `wvcthtmmcmhkybcesirb`):
```sql
with latest as (select id from fanout.sessions where seed_keyword='retatrutide' and status='complete' order by created_at desc limit 1)
select t.name, count(k.*) total,
  count(k.*) filter (where 'keyword_ideas'=any(k.sources)) ideas,
  count(k.*) filter (where 'keyword_suggestions'=any(k.sources)) suggestions,
  count(k.*) filter (where 'query_fanouts'=any(k.sources)) fanouts,
  count(k.*) filter (where 'autocomplete'=any(k.sources)) autocomplete,
  count(k.*) filter (where 'paa_t1'=any(k.sources) or 'paa_t2'=any(k.sources)) paa
from fanout.topics t left join fanout.keywords k on k.topic_id=t.id
where t.session_id=(select id from latest) group by t.name order by total desc;
```

## 7. Working agreements (this build)

- One feature branch per milestone; merge to `main` with `--no-ff` after validation. Never `git commit -am` for NEW files (it skips untracked — bit us once; use explicit `git add`).
- Logical commits; end-of-milestone summary; stop for human review after each milestone.
- All tables under `fanout` schema; real RLS (never `using (true)`); one migration file per change.
- Don't pre-build later milestones. Flag PRD ambiguity, pick the conservative interpretation, surface it.
- The model is `claude-opus-4-7[1m]`; never put the model id in commits/PRs/code.
