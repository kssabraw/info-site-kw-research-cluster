# Handoff — Topic Fanout Tool build

This is a session-continuity doc. **Read `CLAUDE.md` and `docs/topic-fanout-prd-v1_7.md` first** — they hold the locked decisions and the spec. This file captures live state, the immediate next action, and hard-won gotchas not in those docs.

_Last updated: 2026-05-26. Current `main` HEAD: post-RF merge (`cd7d3dc` + this docs sign-off)._

---

## 1. Where the build is

- **M1 — Foundation:** ✅ complete & signed off. Auth, roles, `projects`/`sessions`/`workspace_settings`/`user_profiles` under the `fanout` schema with RLS; FastAPI `/healthz` + `/me` + `/projects`; React login + project list.
- **M2 — Silo discovery + review:** ✅ complete & signed off. Validated on `retatrutide` (clean silos, zero peer-entity leakage) and `mercury` (disambiguation gate fires).
- **M3 — Expansion pipeline:** ✅ complete & signed off (2026-05-24). Per-silo expansion + autocomplete + keyword persistence with source attribution. `keyword_suggestions`/`query_fanouts` run once on the bare seed, fanned to all silos.
- **M4 — Competitor mining + relevance gate + clustering:** ✅ complete & signed off (2026-05-24). Deep-mine selection (§7.2), SERP competitor mining on gated silos + always-mined seed (§7.4), relevance gate w/ junk filter + cross-silo embedding dedup (§7.6), per-silo Louvain clustering → `statistical_clustering_log` (§7.9). Verified live on `retatrutide` (1 gated silo: 3,953 competitor kw, 1,341 active, 4 groupings @ cohesion 0.784). `autocomplete_max` lowered 1500→500. Built on `m4-competitor-clustering`; merged to `main`.
- **M5 — Article planning orchestrator + cross-topic dedup:** ✅ complete & signed off (2026-05-25). Core §7.10 (Opus 4.7 chunked orchestrator, deterministic cross-topic dedup, `clusters`+`coverage_gaps` schema, staged persistence) **plus** a lot more, validated live on `retatrutide` session `ea83f985`: async background execution + status polling (pulled forward from M11 — kills the 5-min wall), generic peer-entity filter (LLM-derived `aliases`/`peer_entities`), **Lever 3** single-silo routing at the gate, **direct mode** (groupings→articles, no LLM), and calibration tooling (`/regate`, `/cluster-preview`, `/routing-diagnostic`, `/lever3-simulate`). Relevance threshold default 0.62→0.52. See `CLAUDE.md` "Active milestone" for the full breakdown + decisions/divergences. Built on `claude/youthful-bohr-8MovM`; merged to `main`.
- **Recursive Fanout (§7.7, Phase 1):** ✅ complete & signed off (2026-05-26). `POST /sessions/{id}/fanout` re-expands each silo's top cluster representatives as sub-anchors (reusing `run_expansion` w/ `include_seed_level=False`), tags them `recursive`, merges into the stored pool, re-gates + re-clusters. Depth-capped at 1; mining off; cost-gated (unconfirmed → 5–8× estimate at HTTP 200, no spend; `confirm_cost:true` → 202). No schema change. Validated live on `retatrutide` (`4ecefaa1`): 1,007 active recursive keywords (~39% of 2,562 active), 0 peer leak, 315 articles @ res 1.2. Built on `claude/pensive-ramanujan-vyJJD`; merged to `main`. Spec: `docs/recursive-fanout-spec.md`.
- **Next — M6 site architecture (PRD §15.1):** not started. RF was the re-sequenced detour; build returns to the PRD sequence.

## 2. Immediate next action (resume here)

**RF is done. Next is M6 — site architecture (PRD §15.1 / §7.11)**, returning to the PRD sequence after the RF detour. Stop for a human go-ahead before building (milestone discipline). Read PRD §7.11 + §15.1 M6 for scope.

**Decision to settle before/at M6:** the **orchestrator-vs-direct planner default** is still unresolved (orchestrator default, direct via `{"direct": true}`). RF was validated with direct mode for volume — decide whether direct becomes the global default. (RF's cost-confirm pattern — unconfirmed `/fanout` returns the estimate at HTTP 200, `confirm_cost:true` spends — is the interim stand-in until the M9 approval gate exists.)

**Calibration workflow that emerged in M5** (reuse it): tuning is done against the **deployed API via browser-console `fetch`** (sandbox has no egress), and results are inspected via the **Supabase MCP tools**, not the UI (no session resume until M7). `/regate` re-runs gate+cluster on the *stored* pool (no DataForSEO) at an overridden threshold / edge / resolution / aliases / peer_entities — the cheap iteration loop. `/cluster-preview` and `/lever3-simulate` are read-only analysis.

## 3. Deploy & infra state (CRITICAL — caused most of the pain this session)

- **`main` is the single deploy branch** for both Railway and Netlify. Milestones are built on `m{N}-...` branches and **merged to `main` (`--no-ff`)** when validated. Do NOT expect deploys from feature branches.
- **Railway** service `info-site-kw-research-cluster` (project `AR Tools`): **Root Directory = `backend`**, Dockerfile build, deploy branch `main`. Public URL **`https://info-site-kw-research-cluster-production.up.railway.app`**. `railway.json` has no `startCommand` (Dockerfile CMD owns port binding). `/healthz` returns the running commit via `RAILWAY_GIT_COMMIT_SHA` — use it to confirm a deploy landed before calibrating.
- **Netlify** site `kw-research-module` (id `dc24cc19-d745-4074-8967-e037f3c5e86a`): base dir `frontend/`, production branch `main`. Env vars set: `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.
- **Supabase** project = **AR-Internal-Tools**, ref **`wvcthtmmcmhkybcesirb`**, URL `https://wvcthtmmcmhkybcesirb.supabase.co`. Accessible via the Supabase MCP tools (apply_migration / execute_sql / get_logs). The `fanout` schema is **exposed in PostgREST** (Settings → API → Exposed schemas) — required, was a manual step.
- **Env var naming gotcha:** Railway provides the keys as **`SUPABASE_SERVICE_KEY`** and **`SUPABASE_KEY`** (AR Tools convention), NOT `SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_ANON_KEY`. `app/config.py` uses `AliasChoices` to accept both. Don't rename the shared Railway vars.
- **Sandbox can't reach** Supabase / Railway / OpenAI / DataForSEO (egress allowlist). PyPI, npm, GitHub API work. So **all live integration validation happens on the deployed stack**, and Supabase introspection happens via the MCP tools (which run server-side).

## 4. Known issues / open items

- **The 5-min synchronous wall — ✅ RESOLVED in M5.** `/expand`, `/plan-articles`, `/regate` now claim the run, submit to a background worker (`app/jobs.py`), and return `202`; the frontend polls `GET /sessions/{id}/summary`. The work runs server-side past the edge cap. Failure reason is stored in `sessions.last_error`. Caveat unchanged: a process restart mid-job strands `status='running'` (no durable queue; recover by starting fresh or resetting status via MCP), and there's still no UI session-resume until M7.
- **M4 ranked_keywords is domain-level, not URL-level.** §7.4 says "per URL ranks 1–20"; DataForSEO's `ranked_keywords` target is a domain, so we dedupe the top URLs to domains and filter rank ≤ 20 server-side. Verified live (3,953 competitor kw on one silo). The filter path (`ranked_serp_element.serp_item.rank_absolute`) is the documented shape; if it's ever wrong the failure is quiet (mining degrades to 0 + degraded notes, no crash).
- **M4 hygiene leftovers (low, not fixed):** dead `insert_keywords` in `storage/silo.py` (replaced by `insert_classified_keywords`); `/expand` has no guard against running before `/finalize` (degrades gracefully — all active, no scoring); two gated silos sharing a domain make duplicate `ranked_keywords` calls (minor cost).
- **M4 stuck-running edge:** the `/expand` run guard (atomic `try_mark_running`) 409s if status is already `running`. A hard crash / deploy mid-run leaves status stuck `running`, so re-running *that* session 409s forever — recover by starting a new session (no resume until M7).
- **M5 calibration learnings (carry into RF):** (a) raw rationale-anchor cosine is the best keyword→silo routing signal of the four tested — silo-name routing dumps everything into one silo; common-mode centering was *worse* and reverted. (b) Routing is ~71% accurate; embeddings are weakly discriminative (everything ≈ the seed). (c) Deep competitor mining of more silos adds raw volume but the gate filters most as off-niche, so the *useful* pool barely grows (~900 active) — **mining is not the lever for more articles; recursive fanout is.** (d) Good config found for `retatrutide`: threshold ~0.50, edge 0.55, Louvain `resolution` 1.2 (the `/expand` default resolution is 1.0 = coarser; re-gate to 1.2 after a fresh expand).
- **RF validation (2026-05-26, session `4ecefaa1`):** confirmed RF generates genuine on-niche keywords — 1,007 active recursive keywords (~39% of the 2,562 active pool), gate kept ~6% of the 18,045 recursive candidates, **0 off-niche peer leakage**. **Caveat — the 10→315 article jump is resolution-confounded:** baseline plan ran at clustering resolution 1.0, the RF run at 1.2, so it entangles "more keywords" with "finer clustering". The clean RF signal is the keyword count, not the article count. **Not yet done:** a clean article-count A/B (re-plan a non-RF session at res 1.2 via cheap `/regate`, compare to 315) to isolate RF's article contribution. Also: the `recursive` source tag is best-effort (per-(silo,keyword); Lever-3 can route a kw to a silo whose source list lacks it) — don't treat the tag count as exact.
- **`gpt-5.4` + `web_search`** (silo discovery) work in prod but were never verifiable from the sandbox; `OPENAI_SILO_MODEL` / `OPENAI_WEB_SEARCH_TOOL` env vars allow correction without a code change. Grounding now also emits per-seed `aliases` + `peer_entities` for the peer filter — unverifiable from the sandbox, so confirm on a fresh live seed.
- **Session resume in the UI:** the data persists at every step, but the frontend can't reopen a session — **deferred to M7** (Project + Session Browser, §9.4). Hence calibration is console+MCP driven (see §2).
- **Test session state:** `ea83f985` (seed typo'd as `retratrutide`; correct spelling supplied via the `aliases` override, now stored). Currently `awaiting_article_planning`, ~893 active, 0 persisted clusters, after a 5-silo deep-mine re-expand at the coarse default resolution 1.0. To resume on it: `/regate` at res 1.2, then `/plan-articles {"direct": true}`.

## 5. Architecture quick map (backend `backend/app/`)

- `main.py` — FastAPI app, CORS, correlation-id middleware, routers.
- `config.py` — `Settings` (pydantic-settings); env aliases; expansion knobs.
- `api/` — `health.py`, `projects.py`, `sessions.py`. Session endpoints: silo discovery, `/finalize`, `/deep-mine`, `/expand` (async), `/plan-articles` (async; body `{"direct": true}` skips the orchestrator), `/regate` (async; body overrides threshold/edge/resolution/aliases/peer_entities), `/fanout` (async; RF §7.7 — cost-gated, `{"confirm_cost": true}` to spend, optional resolution/threshold overrides), `/summary` (poll), `/clusters` (read), `/cluster-preview`, `/routing-diagnostic`, `/lever3-simulate` (read-only analysis).
- `auth/dependencies.py` — `require_user` (verifies Supabase JWT via service client; logs real reason on failure).
- `storage/supabase_client.py` — service client (RLS-bypass, admin writes) + user client (anon key + user JWT, RLS-enforced reads). `storage/silo.py` — session/topic/keyword/cluster DB ops incl. `set_topics_gating`, `get_topic_embeddings`, `insert_classified_keywords`, `try_mark_running`, `get_session`, `list_all_keyword_pool` (re-gate pool reconstruction), `persist_article_plan` (staged cluster write), `reset_article_planning`, `get_pipeline_summary`, `list_clusters`.
- `llm/openai_client.py` — GPT-5.4 grounding + silo proposal (Responses API + web_search) + `embed()`.
- `dataforseo/client.py` — DataForSEO calls (demand sample, SERP structure, expansion endpoints, autocomplete; M4: `serp_top_urls`, `ranked_keywords`, `domain_of`).
- `pipeline/` — `silo_discovery.py` (M2), `expansion.py` (M3), `competitor.py`/`relevance.py`/`clustering.py` (M4), `orchestrate.py` (M4 `run_refinement_pipeline` + M5 `gate_and_cluster`/`cluster_preview`/`routing_diagnostic`/`simulate_best_silo_clustering`), `models.py`.
- `pipeline/article_planning/` (M5) — `orchestrate_articles.py` (chunked orchestrator + `direct` mode), `dedup.py`, `serp.py`, `models.py`. `jobs.py` (M5) — async background worker (M6/RF: `run_fanout_job`). `llm/anthropic_client.py` — Opus 4.7 tool-use client. `relevance.py` now also does the peer-entity filter + Lever-3 routing.
- `pipeline/recursive_fanout.py` (RF §7.7) — `derive_sub_anchors` (top-N cluster reps per silo), `run_recursive_expansion` (reuses `run_expansion`, remaps synthetic sub-anchor topics back to parent silos, tags `recursive`), `merge_into_pool`. Drives `run_fanout_job`.

Frontend: `frontend/src/owner/SiloDiscovery.tsx` is the whole flow (seed → disambiguation → silo review → finalize → **deep-mine selection** → run pipeline → results). `shared/api.ts`, `shared/auth.tsx`, TanStack Query. Progress UI = `WorkingProgress` (discovery ~20–40s; pipeline ~3–6 min estimate).

Schema migrations in `supabase/migrations/`: `..._fanout_initial.sql` (M1), `..._topics.sql` (M2), `..._keywords.sql` (M3), `..._keywords_relevance.sql` (M4), `...20260525000000_clusters.sql` (M5: `clusters` + `coverage_gaps` + orchestrator keyword cols + `awaiting_article_planning` status), `..._session_last_error.sql` (M5), `..._peer_entities.sql` (M5: `sessions.aliases` + `peer_entities`). All applied to the live DB.

## 6. Useful commands / queries

Backend (from `backend/`, venv at `.venv`):
```bash
. .venv/bin/activate
python -m pytest -q          # 84 tests, all passing
ruff check app/ tests/
python -c "import app.main"   # import smoke test
```
Frontend (from `frontend/`): `npm run build` (tsc + vite).

Per-silo / per-source breakdown for the latest run (run via Supabase MCP `execute_sql`, project `wvcthtmmcmhkybcesirb`):
```sql
with latest as (select id from fanout.sessions where seed_keyword ilike 'ret%rutide' order by created_at desc limit 1)
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
