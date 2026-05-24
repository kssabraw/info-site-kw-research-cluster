# Handoff — Topic Fanout Tool build

This is a session-continuity doc. **Read `CLAUDE.md` and `docs/topic-fanout-prd-v1_7.md` first** — they hold the locked decisions and the spec. This file captures live state, the immediate next action, and hard-won gotchas not in those docs.

_Last updated: 2026-05-24. Current `main` HEAD: `ff9d89e`._

---

## 1. Where the build is

- **M1 — Foundation:** ✅ complete & signed off. Auth, roles, `projects`/`sessions`/`workspace_settings`/`user_profiles` under the `fanout` schema with RLS; FastAPI `/healthz` + `/me` + `/projects`; React login + project list.
- **M2 — Silo discovery + review:** ✅ complete & signed off. Validated on `retatrutide` (clean silos, zero peer-entity leakage) and `mercury` (disambiguation gate fires).
- **M3 — Expansion pipeline:** ⏳ **built & deployed, validation in progress.** Per-silo DataForSEO expansion + autocomplete + keyword persistence all work. **Open issue:** `keyword_suggestions` and `query_fanouts` return 0 across all silos (see §4 — this is the active task).
- **M4+ — not started.**

## 2. Immediate next action (resume here)

We added a **temporary owner-only debug endpoint** to see why `keyword_suggestions`/`query_fanouts` return empty, instead of guessing (already fixed it blind twice).

1. Confirm Railway is on `ff9d89e` (`…up.railway.app/healthz` → `"commit":"ff9d89e..."`). NOTE: commit `2430292` was broken (imported `app.api.debug` without shipping the file); `ff9d89e` fixes it.
2. In the browser console on `kw-research-module.netlify.app` (logged in), run:
   ```js
   const t = JSON.parse(localStorage.getItem('sb-wvcthtmmcmhkybcesirb-auth-token')).access_token;
   const r = await fetch('https://info-site-kw-research-cluster-production.up.railway.app/debug/dataforseo?keyword=retatrutide', {headers:{Authorization:'Bearer '+t}});
   console.log(JSON.stringify(await r.json(), null, 2));
   ```
3. From the output, fix in `backend/app/dataforseo/client.py` + `backend/app/pipeline/expansion.py`:
   - **`keyword_suggestions`** is a *phrase-match* endpoint (returns keywords containing the anchor). The long seed-qualified anchor (`"retatrutide Obesity & Metabolic Uses"`) matches nothing → 0. Fix = give this endpoint a *tight* anchor (likely the seed, or seed + a short term), separate from `keyword_ideas`' broad anchor. Implement **per-endpoint anchors**.
   - **`query_fanouts`** (mapped to Labs `related_keywords`) returns 0 even after a parse fix — confirm the real item shape from the probe and correct the parser, or swap the endpoint.
4. **Remove the debug endpoint** (`backend/app/api/debug.py`, the `raw()` method in `client.py`, and the router include in `main.py`) once tuning is done.
5. Re-run `retatrutide`; verify per-silo/per-source counts via Supabase (query in §6). Then **sign off M3** and start **M4**.

## 3. Deploy & infra state (CRITICAL — caused most of the pain this session)

- **`main` is the single deploy branch** for both Railway and Netlify. Milestones are built on `m{N}-...` branches and **merged to `main` (`--no-ff`)** when validated. Do NOT expect deploys from feature branches.
- **Railway** service `info-site-kw-research-cluster` (project `AR Tools`): **Root Directory = `backend`**, Dockerfile build, deploy branch `main`. `railway.json` has no `startCommand` (Dockerfile CMD owns port binding). `/healthz` returns the running commit via `RAILWAY_GIT_COMMIT_SHA`.
- **Netlify** site `kw-research-module` (id `dc24cc19-d745-4074-8967-e037f3c5e86a`): base dir `frontend/`, production branch `main`. Env vars set: `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.
- **Supabase** project = **AR-Internal-Tools**, ref **`wvcthtmmcmhkybcesirb`**, URL `https://wvcthtmmcmhkybcesirb.supabase.co`. Accessible via the Supabase MCP tools (apply_migration / execute_sql / get_logs). The `fanout` schema is **exposed in PostgREST** (Settings → API → Exposed schemas) — required, was a manual step.
- **Env var naming gotcha:** Railway provides the keys as **`SUPABASE_SERVICE_KEY`** and **`SUPABASE_KEY`** (AR Tools convention), NOT `SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_ANON_KEY`. `app/config.py` uses `AliasChoices` to accept both. Don't rename the shared Railway vars.
- **Sandbox can't reach** Supabase / Railway / OpenAI / DataForSEO (egress allowlist). PyPI, npm, GitHub API work. So **all live integration validation happens on the deployed stack**, and Supabase introspection happens via the MCP tools (which run server-side).

## 4. Known issues / open items

- **M3:** `keyword_suggestions` + `query_fanouts` return 0 (active task, §2). The pool is still solid without them (~1,900 seed-relevant kw/silo from `keyword_ideas` + `autocomplete` + PAA).
- **`gpt-5.4` + `web_search`** (silo discovery) work in prod but were never verifiable from the sandbox; `OPENAI_SILO_MODEL` / `OPENAI_WEB_SEARCH_TOOL` env vars allow correction without a code change.
- **Expansion is synchronous** and can run up to the 4-min hard cap (`EXPANSION_TIME_BUDGET_S=240`). A long run can outrun the browser/gateway connection even though the backend finishes (happened once — 17k keywords saved, UI never got the response). Real fix = background job + polling, **deferred to M11**. Mitigation knobs: `EXPANSION_MAX_WORKERS` (raise to ~24 to finish faster), `AUTOCOMPLETE_MAX` (lower to cut time/cost). Time cap is wall-clock only (abandoned in-flight calls may still bill).
- **Session resume in the UI:** the data persists at every step, but the frontend can't reopen a session — **deferred to M7** (Project + Session Browser, §9.4).
- **`status: complete`** is set at the end of M3 expansion as the "current pipeline terminus"; later milestones must move this downstream.
- **Review leftovers (Low, not fixed):** R4 — `build_anchor` uses substring containment (a seed that's a substring of a silo word skips seed-qualification); R5 — `except TimeoutError` for the time cap relies on Python ≥3.11 (we pin 3.11).

## 5. Architecture quick map (backend `backend/app/`)

- `main.py` — FastAPI app, CORS, correlation-id middleware, routers.
- `config.py` — `Settings` (pydantic-settings); env aliases; expansion knobs.
- `api/` — `health.py`, `projects.py`, `sessions.py` (silo discovery + M3 expansion endpoints), `debug.py` (TEMP, remove).
- `auth/dependencies.py` — `require_user` (verifies Supabase JWT via service client; logs real reason on failure).
- `storage/supabase_client.py` — service client (RLS-bypass, admin writes) + user client (anon key + user JWT, RLS-enforced reads). `storage/silo.py` — session/topic/keyword DB ops.
- `llm/openai_client.py` — GPT-5.4 grounding + silo proposal (Responses API + web_search) + embeddings.
- `dataforseo/client.py` — DataForSEO calls (demand sample, SERP structure, expansion endpoints, autocomplete, `raw()` for debug).
- `pipeline/silo_discovery.py` (M2), `pipeline/expansion.py` (M3), `pipeline/models.py`.

Frontend: `frontend/src/owner/SiloDiscovery.tsx` is the whole flow (seed form → disambiguation → silo review → finalize → run expansion → results). `shared/api.ts`, `shared/auth.tsx`, TanStack Query. Progress UI = `WorkingProgress` component (discovery ~20–40s, expansion ~2–4 min estimates).

Schema migrations in `supabase/migrations/`: `..._fanout_initial.sql` (M1), `..._topics.sql` (M2), `..._keywords.sql` (M3). All applied to the live DB.

## 6. Useful commands / queries

Backend (from `backend/`, venv at `.venv`):
```bash
. .venv/bin/activate
python -m pytest -q          # 25 tests, all passing
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
