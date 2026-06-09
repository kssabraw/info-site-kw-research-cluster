# Handoff — Topic Fanout Tool build

This is a session-continuity doc. **Read `CLAUDE.md` and `docs/topic-fanout-prd-v1_7.md` first** — they hold the locked decisions and the spec. This file captures live state, the immediate next action, and hard-won gotchas not in those docs.

_2026-06-09 (≤5 links/page): **Capped internal links at 5 per page; re-based the
no-orphan guarantee on a within-silo article cycle** (owner rule). Commit `78b403c`
on `claude/wonderful-cray-wo84am`. Pillars were linking DOWN to **every** child
article (60+ links on big silos) — and that was *also* the §15.2 #3 no-orphan
mechanism, so capping it naively would orphan the unlinked children. New topology
(all deterministic, acceptance rules hold by construction): **pillar page** = up to
3 down-links to the silo's **most-central children** (nearest the silo mean centroid)
+ up to 2 peer-pillar laterals = ≤5 (small silos ≤3 articles still link to all
children); **article page** = 1 up-link + up to 4 laterals = ≤5, where **one lateral
slot is the within-silo cycle successor** (article i→i+1, last→first) so every
article is some peer's successor and gets ≥1 inbound link — the new no-orphan
guarantee, independent of the pillar's link count. `supporting_article_ids` is now
the pillar's **capped down-LINK list**, not full membership (membership is
recoverable from each article's `parent_pillar_topic_id`, which the frontend already
uses to build the site map — so **no UI change**; the cap flows straight into the
architecture CSV `internal_links_out`). New config: `architecture_pillar_down_links_max=3`,
`pillar_lateral_links_max` 5→2, `lateral_article_links_max` 3→4 (`generate.py`
`_pillar_down_links` + a `successor` arg on `_lateral_article_links`). 297 backend
tests pass (1 new `test_large_silo_caps_pillar_links_and_keeps_no_orphans_via_cycle`),
ruff clean. **Applies to newly-generated architectures** — regenerate an existing
session's architecture to apply the cap retroactively. Flagged divergence from PRD
§7.11/§15.2 #3 (the no-orphan mechanism changed, the property is preserved)._

_2026-06-09 (migration sweep): **All 14 `fanout` migrations are applied to prod —
no further gaps** (read-only existence check of each migration's key object against
the live DB, since migration tracking uses apply-time timestamps not repo prefixes,
so version numbers can't be compared directly). After today's `filtered_language`
fix the `fanout` schema is fully in sync. The enum-drift failure mode specifically
(`ALTER TYPE … ADD VALUE`) appears in only **one** repo migration — the
`filtered_language` one, now applied; every other enum is created complete in its
`CREATE TYPE`, so that class of bug is closed. (The live DB also carries `public`-
schema migrations from the shared AR-Internal-Tools app — `sie_cache`, `clients_*`,
`local_seo_pages`, etc. — which are not this app's and are expected.) Reusable sweep
query is a `with checks(migration, kind, present) as (values …)` of `to_regclass` /
`information_schema.columns` / `pg_enum` existence tests — re-run it after any deploy
that ships a new migration._

_2026-06-09 (writer ownership): **H2 outlines moved out of the pipeline — the
writer owns them** (owner decision; resolves §9.9 #3, extended to pillars). Commit
`67c1c2c` on `claude/wonderful-cray-wo84am`. The M5 orchestrator no longer emits
`suggested_h2s` and the M6 architect no longer emits `h2_outline` (both dropped from
the LLM tool schema + prompt — also trims output tokens); every article/pillar is
persisted with an **empty** outline. The `clusters.h2_outline` column and the
`suggested_h2s`/`h2_outline` model fields are **kept** (always empty for now) so
storage, API models, frontend types and the architecture CSV all keep working and
the writer module (M12+) has a destination to fill at write time. **Until the writer
ships, the Architecture view + architecture-CSV `outline_h2s` are blank** — intended.
Flagged divergence from PRD §7.10/§7.11. Tests: 296 pass (2 `test_architecture`
assertions updated to expect empty outlines), ruff clean; the only failures are 5
pre-existing `test_health` auth artifacts (401 vs 403) from the sandbox auth config,
unrelated to this change._

_2026-06-09 (validation run): **Applied a missed migration to prod — language
filter enum (`filtered_language`).** The first deployed validation run (session
`727b253a`, seed "how to rank a plumber in chatgpt") failed mid-expand with
`invalid input value for enum keyword_status: "filtered_language"`. **Root cause: a
code-before-migration deploy gap.** The pre-embedding language filter (commit
`ad17a54`, on `main` since 2026-06-04) tags non-English keywords with a new
`keyword_status` value, but its migration `20260604000001_keyword_status_filtered_
language.sql` had **never been applied to the live DB** — the live enum had only the
6 original values. The `/summary` read path was guarded against this (safe-count
helper), but the **gate's keyword-write path was not**, so it hard-errored when
persisting a `filtered_language` keyword. **Fix: applied `20260604000001` to the
live DB via Supabase MCP** (enum now has 7 values incl. `filtered_language`); no
code change, and **no language-picker is needed** — the filter is automatic. The
failed run spent **~$3.94** (real DataForSEO, metered correctly on failure — a live
confirmation of §16.4 "partial cost persists on failure") but persisted **0
keywords** (the write rolled back), so it can't be cleanly resumed — recover by
starting a fresh session (same DataForSEO re-spend either way, cleaner cost number).
**Lesson: when deploying a branch that adds a migration, apply the migration to prod
via MCP as part of the deploy** — the repo file alone doesn't touch the live DB.
Validation continues on a fresh run._

_2026-06-09 (later): **Two post-M11 cost fixes during live validation (Track A,
items 1–4).** Both on `claude/wonderful-cray-wo84am`; backend tests pass (52 run:
approvals + cost_meter + roles + cost), ruff clean. **(1) Opus LLM rate
calibrated.** `cost_meter.py` `_LLM_RATES` rated `claude-opus-4-7` at (15, 75)
USD/1M tok — a flagged estimate. The published Opus 4.7/4.8 list price is **(5, 25)**;
the old value was **3× too high**, inflating the LLM-heavy `article_planning` +
`architecture` phases of `actual_cost_usd`/`cost_breakdown`. Corrected to (5, 25),
added `claude-opus-4-8` at the same rate, updated `test_cost_meter.py`. DataForSEO
cost is the real per-call charge and was unaffected; `gpt-5.4`/embedding rates left
as-is (silo_discovery meters within cents of §8.1). This closes §2's "recalibrate
`_LLM_RATES`" item. **(2) `estimated_cost_usd` now persisted on every run path.**
It was written only by `submit-for-approval` (the VA over-cap path), so **owner runs
and under-cap VA "Run now" runs left it NULL** — the §8.4 cost banner reads the
stored column off `GET /summary`, so on those (most common) paths it had no estimate
to compare the live actual against (confirmed: all 3 live metered sessions had
`estimated_cost_usd: NULL`). `POST /expand` now computes the §8.1 estimate once (it
already needed it for the VA gate) and persists it when the run is claimed; the
approval path still writes its own at submit time, and an owner-approved run (kicked
via `jobs.submit_expand`) keeps that one, so no path double-writes. `test_approvals`
updated. **Both fixes take effect only after merge to `main` + Railway redeploy** —
a validation run before then still shows the old behavior. Live-probe findings while
validating: deployment current (Railway redeployed 2026-06-09 02:12 UTC on latest
`main`), the M11 meter is working in prod (3 sessions carry real `actual_cost_usd` +
per-phase `cost_breakdown`), and **§7.8 metrics enrichment is now built** (migration
`keyword_metrics` shipped 2026-05-29) — so the M11 checklist note that "+metrics
can't be exercised" is stale. Item 4 (nested-thread `external_call` logs carrying
`cost_usd` + non-null `session_id`) still needs a fresh pipeline run on the current
deploy — none has happened post-redeploy._

_Last updated: 2026-06-09. **§9 added — Blog Writer module integration plan.**
After reviewing the AR Tools Blog Writer PRD bundle (8 PRDs), locked direction:
port **only the Writer module** (PRD #1, v1.7) into `backend/app/writer/` in
degraded mode (`1.7-no-context`, `no_citations: true`) + a deterministic
cluster→brief **adapter** + a deterministic **internal-link injector**. Skip
Brief Generator / SIE / Research / Sources Cited modules. Per-article publish
dates with bulk **`Schedule all`** (all-at-once OR drip N/day, ≤365d,
pillars-first, every calendar day, whole-session scope) using **absolute URLs**
that require `sessions.site_base_url`. Worker is an **in-process asyncio loop**
in the existing backend (matches M5 `app/jobs.py`; CLAUDE.md scheduler-
confirmation requirement met). Implicitly shifts §8.5 #1 to a third option
(neither AR-Internal-Tools `runs` coupling nor a full duplicate). M12/M13
sketch in §9.10. **Nothing built** — see §9 for the full plan + open decisions
in §9.9._

_2026-06-05: **Post-M11 site-creation planning** — captured in §8.
Two-template (informational + local SEO, one-site-per-business) site generation
pipeline orchestrating existing writer apps. Writer landscape discovered via
MCP probing 2026-06-05: **AR-Internal-Tools `public` schema is a 5-module content
production pipeline** (brief → SIE → research → **writer** → sources_cited) — the
natural informational writer, sitting in the SAME Supabase as this app (no cross-DB
coordination needed). ShowUP Local on its own Supabase is the local-SEO option.
Coordination decided: **shared Postgres queue (Option C)** — orchestrator inserts
work rows, writer claims via `SELECT … FOR UPDATE SKIP LOCKED`, mirrors the M5
`app/jobs.py` pattern. **Nothing built.** Seven open decisions in §8.5 to resolve
before drafting M12. M11 still pending review + live validation per §2. Security
finding to address before M12 ships: `AR-Internal-Tools.public.sie_cache` has RLS
disabled (§8.7). Prior milestone summary follows._

_2026-05-29: **M11 (cost + observability, §16) complete — the FINAL milestone;
M1–M11 all built.** Pending review + live validation (sandbox egress). Built on
`claude/exciting-davinci-tZGwH` (off `main` `4b10ed2`); **not yet merged to `main`**
— the owner decides the merge. Real-metered per-step cost attribution
(`app/cost_meter.py` `CostMeter`: DataForSEO's real per-call charge + token-derived
LLM cost) flushed live to `sessions.actual_cost_usd` + a new `cost_breakdown` jsonb
every 10s from the background jobs (`app/cost_attribution.py`), cumulative across a
session's runs. `app/concurrency.py::ContextThreadPoolExecutor` propagates the
meter + `session_id`/`correlation_id` into the pipeline's nested API-call threads
(also fixes a latent §16.3 gap where those logs had `session_id: null`). `GET
/summary` carries a live `cost` block → `shared/CostBanner.tsx` on the Owner
workspace + VA progress screen. Owner-only `GET /sessions/{id}/debug` + `owner/
DebugView.tsx` expose `statistical_clustering_log` + `orchestrator_log` + cost
(§15.3 #8). Migration `20260529000000_session_cost_breakdown.sql` applied live via
MCP. 176 backend tests (11 new) + ruff clean, frontend builds strict-clean. **Live
cost numbers / banner / debug view NOT sandbox-validated.** With M11 there is no
next milestone to build — what's left is the §15.3 live-validation checklist (§2
below). The prior M10 entry follows._

_M10 (CSV export, §12) **complete & merged to `main`** (per owner instruction;
merged `--no-ff`, remote `main` was at the M9 merge `1e0db30`, conflict-free) —
built on `claude/wonderful-allen-oTKaO`. Three formats (flat / topic_grouped as a
`.zip` / architecture) from current Postgres state via **pure, unit-tested**
builders (`backend/app/csv_export.py`); backend uploads to the new private
**`csv-snapshots`** Storage bucket and serves a time-limited signed URL
(`storage/exports.py`, **deploy-only — sandbox can't reach Storage**); new router
`api/exports.py`; migration `20260528000000_csv_exports.sql` + the bucket
**applied live via MCP**; frontend **Exports tab** on both Owner + VA workspaces.
CSV formula-injection hardened._

_M9 (approval workflow, §11.3) **complete & merged to `main`** (per owner instruction; merged `--no-ff`, remote `main` was at `27f5731`, conflict-free) — built on `claude/jolly-heisenberg-Z06PH` (this session's pinned branch). **No schema/migration** (all approval columns + statuses exist from M1). New pure cost model (`backend/app/cost.py`, §8.1-derived); the approval gate sits at the cost-bearing `/expand` (conservative read of §11.3). New endpoints: `/workspace-settings`, `/sessions/{id}/cost-estimate`, `/submit-for-approval` + `/cancel-approval` (VA), `/approvals` + `/approve` + `/reject` (owner-only); `/summary` gained an `approval` block. Frontend: wizard CostStep fetches the real estimate + branches Run-now vs Submit-for-approval → WaitingStep (30s poll, cancel, adjust-&-resubmit); Owner Approvals page + nav badge. 139 backend tests (9 cost + 14 approvals new) + ruff clean; frontend builds strict-clean. **NOT browser-validated** (sandbox egress) — validate VA submit → Owner approve/reject → VA-sees-decision on the deployed stack. M8 is also still not browser-validated. Next: M10 (CSV export, §12)._

---

## 1. Where the build is

- **M1 — Foundation:** ✅ complete & signed off. Auth, roles, `projects`/`sessions`/`workspace_settings`/`user_profiles` under the `fanout` schema with RLS; FastAPI `/healthz` + `/me` + `/projects`; React login + project list.
- **M2 — Silo discovery + review:** ✅ complete & signed off. Validated on `retatrutide` (clean silos, zero peer-entity leakage) and `mercury` (disambiguation gate fires).
- **M3 — Expansion pipeline:** ✅ complete & signed off (2026-05-24). Per-silo expansion + autocomplete + keyword persistence with source attribution. `keyword_suggestions`/`query_fanouts` run once on the bare seed, fanned to all silos.
- **M4 — Competitor mining + relevance gate + clustering:** ✅ complete & signed off (2026-05-24). Deep-mine selection (§7.2), SERP competitor mining on gated silos + always-mined seed (§7.4), relevance gate w/ junk filter + cross-silo embedding dedup (§7.6), per-silo Louvain clustering → `statistical_clustering_log` (§7.9). Verified live on `retatrutide` (1 gated silo: 3,953 competitor kw, 1,341 active, 4 groupings @ cohesion 0.784). `autocomplete_max` lowered 1500→500. Built on `m4-competitor-clustering`; merged to `main`.
- **M5 — Article planning orchestrator + cross-topic dedup:** ✅ complete & signed off (2026-05-25). Core §7.10 (Opus 4.7 chunked orchestrator, deterministic cross-topic dedup, `clusters`+`coverage_gaps` schema, staged persistence) **plus** a lot more, validated live on `retatrutide` session `ea83f985`: async background execution + status polling (pulled forward from M11 — kills the 5-min wall), generic peer-entity filter (LLM-derived `aliases`/`peer_entities`), **Lever 3** single-silo routing at the gate, **direct mode** (groupings→articles, no LLM), and calibration tooling (`/regate`, `/cluster-preview`, `/routing-diagnostic`, `/lever3-simulate`). Relevance threshold default 0.62→0.52. See `CLAUDE.md` "Active milestone" for the full breakdown + decisions/divergences. Built on `claude/youthful-bohr-8MovM`; merged to `main`.
- **Recursive Fanout (§7.7, Phase 1):** ✅ complete & signed off (2026-05-26). `POST /sessions/{id}/fanout` re-expands each silo's top cluster representatives as sub-anchors (reusing `run_expansion` w/ `include_seed_level=False`), tags them `recursive`, merges into the stored pool, re-gates + re-clusters. Depth-capped at 1; mining off; cost-gated (unconfirmed → 5–8× estimate at HTTP 200, no spend; `confirm_cost:true` → 202). No schema change. Validated live on `retatrutide` (`4ecefaa1`): 1,007 active recursive keywords (~39% of 2,562 active), 0 peer leak, 315 articles @ res 1.2. Built on `claude/pensive-ramanujan-vyJJD`; merged to `main`. Spec: `docs/recursive-fanout-spec.md`.
- **M6 — Site architecture (PRD §15.1 / §7.11):** ✅ **complete & signed off (2026-05-26).** `POST /sessions/{id}/architecture` (async, 202) builds one **pillar** per article-bearing silo: Opus 4.7 (reusing the orchestrator client) writes each pillar's editorial fields (title / target keyword / summary / 5–8 H2s) once per pillar in parallel; the **internal linking matrix is assembled deterministically** so the §15.2 rules hold by construction — one pillar/silo, every article up-links to its pillar + pillar down-links to all its articles (⇒ no orphans), pillars link laterally only where topic-embedding cosine > 0.55, and each article gets 2–3 lateral peers (prioritizing M5's `peer_article_links`, filled by same-silo centroid). Persists one `site_architecture` row/session (`session_id` PK, upsert on regenerate per §9.3). `GET /sessions/{id}/architecture` reads it (404 until generated); `GET /summary` now carries an `architecture` block for polling. Per-pillar LLM failure → deterministic stub; all-degraded → `error`. **Validated live on `retatrutide` `4ecefaa1`** (315 clusters, 5 silos): 5 pillars, 0 skipped, 315 supporting articles, **0 orphans, 0 bad parent refs, 945 lateral links (0 dangling)**, all 10 pillar pairs cosine [0.77, 0.85] (>0.55 holds) — all four §15.2 criteria pass; titles are strong (e.g. "How to Get Retatrutide: The Complete Guide to Access, Cost…"). New code: `pipeline/architecture/` (`models.py`, `generate.py`), `run_architecture_job`/`submit_architecture` in `jobs.py`, the two endpoints in `api/sessions.py`, storage helpers (`persist_architecture`, `get_architecture`, `get_cluster_centroids`, `get_keyword_texts`), migration `20260526000000_site_architecture.sql`, `api.ts` (`generateArchitecture`/`getArchitecture` + types). **Post-review fix:** `reset_article_planning` now also clears `site_architecture` (a re-plan/regate/fanout re-creates clusters with fresh ids, so the old architecture would otherwise dangle). **Concurrency fix:** `architect_max_workers` 5→2 + backoff before reprompt — the first live run degraded 3/5 pillars to stubs (transient Anthropic rate-limit under 5 parallel calls, not size-related); the re-run gave 0/5 degraded. Built on `claude/gifted-clarke-pONCI`; merged to `main`. Migration applied to the live DB via Supabase MCP (recorded as version `20260526050706` — the project's migration tracking uses apply-time timestamps, not the repo file prefixes, for every migration).
- **M7 — Owner UI (PRD §15.1 / §9):** ✅ **complete & merged to `main`** (this session, built on `claude/sweet-ramanujan-PXvK0`, merged `--no-ff`). The three views + Split + Project/Session Browser, all editing operations, browser archive/move/delete. An adversarial review pass + fixes ran before merge (architecture invalidation on structural edits; primary-membership guards; idempotent accept-gap). See `CLAUDE.md` "Active milestone" for the full M7a/M7b breakdown + decisions/divergences. Backend 98 tests pass, ruff clean; frontend builds. **Not yet browser-tested** (sandbox egress) — validate on the deployed stack. Remote `main` was at the M6 sign-off (`03c3e54`); the merge added only the M7 commits (`03c3e54..84f96b9`, conflict-free).
- **M8 — VA wizard (PRD §15.1 / §10):** ✅ **complete & merged to `main` (2026-05-26, per owner instruction).** Role-gated app: `App.tsx` reads `me.role` and routes owners to the §9 Owner UI (unchanged) and VAs to a new 9-step linear wizard (`frontend/src/va/Wizard.tsx`) + a restricted results surface. Step gating per §10.1 (disambiguation only when ambiguous; settings limited to topic_count + coverage_mode; deep-mine capped at seed + 2; cost confirmation **stubbed to "Run now"** — approval is M9; progress auto-chains expand → plan-articles). Restricted results reuse the Owner views via a new `role` on `SessionWorkspace`'s `SessionCtx`: VA = Table + Cluster + read-only Architecture (no Split); Cluster = rename + move-keyword only; Table bulk = covered + move only; "Request restructure" is a local stub. **Server-side enforcement** (defense in depth — service-role writes bypass RLS): new `require_owner` dep + `get_role()` (`app/auth/dependencies.py`) gate cluster delete/merge/split/promote-primary, gap accept/dismiss, `/architecture`, session delete, `/regate` + calibration tools, `/fanout`; in-handler checks for the deep-mine cap (`va_deep_mine_max_silos=2`), VA rename-only `PATCH /clusters`, VA no-exclude bulk status. 116 tests (18 new in `tests/test_roles.py`), ruff clean; frontend builds. Built on `claude/exciting-cannon-jTTVb`, merged `--no-ff` to `main`. No schema change. Flagged: architecture owner-only (VA run ends at the plan; Architecture tab owner-pending), metrics toggle decorative (§7.8 unbuilt), no "+ New project" (no endpoint), static cost band.
- **M9 — Approval workflow (PRD §15.1 / §11.3):** ✅ **complete & merged to `main`** (per owner instruction, merged `--no-ff`, conflict-free; still pending live validation). Real cost estimate (pure `app/cost.py`, §8.1-derived); the approval gate sits at the cost-bearing `/expand` (conservative read of §11.3 — silo discovery already runs at `POST /sessions`). VA wizard: CostStep fetches the authoritative estimate and branches under-cap → **Run now** vs over-cap/recursive → **Submit for approval** → **WaitingStep** (polls `/summary` every 30s; cancel; on reject shows the Owner's note + adjust-&-resubmit). Owner: **Approvals** page (`/approvals`) + decision modal (approve/reject + note) + an AppShell nav badge (owner-only, 30s poll). New endpoints: `GET /workspace-settings`, `GET /sessions/{id}/cost-estimate?gated_count=N`, `POST /sessions/{id}/submit-for-approval` + `/cancel-approval` (require_user), `GET /approvals` + `POST /sessions/{id}/approve` + `/reject` (require_owner); `/summary` carries an `approval` block. **No schema change** (M1 already had the columns + `pending_approval`/`rejected`). 139 backend tests (9 in `test_cost.py`, 14 in `test_approvals.py`) + ruff clean; frontend builds. Built on `claude/jolly-heisenberg-Z06PH`, merged `--no-ff` to `main` (conflict-free). See `CLAUDE.md` "Active milestone" for the full breakdown + decisions/divergences (gate placement, reject reuses the session, queue submitted-at = created_at, owner-offline chaining gap, recursive not a VA control).
- **M10 — CSV export (PRD §15.1 / §12):** ✅ **complete & merged to `main`** (per owner instruction, merged `--no-ff`, conflict-free; still pending live validation). Three formats from current Postgres state via pure builders (`backend/app/csv_export.py`): flat (one row/keyword, §9.1 cols, Volume/KD/CPC blank), topic_grouped (one CSV/topic → single `.zip`), architecture (one row/page; 400 if no architecture). Backend uploads to the private `csv-snapshots` bucket + serves a signed URL (`storage/exports.py`); new router `api/exports.py`. Migration `20260528000000_csv_exports.sql` (`fanout.csv_exports` + real RLS) + the bucket applied live via MCP. Frontend Exports tab on both Owner + VA. 164 backend tests + ruff clean, frontend builds. **Storage upload / signed URLs / live round-trip NOT sandbox-validated — deploy-only.** See `CLAUDE.md` "Active milestone" for full decisions/divergences.
- **M11 — Cost confirmation + observability (PRD §15.1 / §16):** ✅ **complete, pending review + live validation** (built on `claude/exciting-davinci-tZGwH`, not yet merged). Real-metered per-step cost → `actual_cost_usd` + new `cost_breakdown` jsonb, flushed live every 10s from the jobs (`app/cost_meter.py` + `app/cost_attribution.py`); `ContextThreadPoolExecutor` (`app/concurrency.py`) propagates the meter + correlation/session ids into nested pipeline threads; the four external-call sites populate `cost_usd`; live cost banner on `/summary` (`shared/CostBanner.tsx`) on Owner + VA; owner-only `GET /sessions/{id}/debug` + `owner/DebugView.tsx` (clustering + orchestrator logs + cost). Migration `20260529000000_session_cost_breakdown.sql` applied live via MCP. 176 backend tests + ruff clean; frontend builds. See `CLAUDE.md` "Active milestone" for full decisions/divergences. **With M11 the M1–M11 build sequence is done — no next milestone; remaining work is live validation (§2).**

## 2. Immediate next action (resume here)

**M11 is built on `claude/exciting-davinci-tZGwH` but NOT merged.** The owner
decides the merge (milestone discipline). The `cost_breakdown` migration is already
applied to the live DB via MCP, so once the branch merges to `main` the Railway +
Netlify deploys will be schema-consistent. **With M11, the M1–M11 build is complete
— there is no next milestone to start.** What remains is the §15.3
Definition-of-Done live validation that the sandbox can't run (no egress).

**M11 live-validation checklist (deploy the branch first):**
1. Run a standard, metrics-off session through to `complete` (`/expand` →
   `/plan-articles` → `/architecture`). While it runs, confirm the **cost banner**
   on the Owner workspace (and the VA wizard progress screen) shows a climbing
   "Cost so far" that updates roughly every poll (~4s UI / 10s flush).
2. On the completed session, confirm `actual_cost_usd` lands **within ±25% of the
   §8.1 standard estimate (~$2.80)** — §15.3 #7. (Metrics-off only; §7.8 is
   unbuilt, so the "+metrics" line can't be exercised.) If LLM cost is wildly off,
   recalibrate the `_LLM_RATES` / `_EMBED_RATES` constants in `app/cost_meter.py`
   against the real OpenAI/Anthropic invoices (the rates are estimates; DataForSEO
   cost is the real per-call charge, so error is LLM-side).
3. As **owner**, open **Debug** (link in the session workspace head → `/session/
   :id/debug`): confirm the per-step **cost_breakdown table**, the
   **orchestrator_log** (merge/split/drop rationales + dedup collisions), and the
   **statistical_clustering_log** all render. As a **VA**, confirm `GET
   /sessions/{id}/debug` → **403** (and the Debug link/route are absent).
4. Inspect Railway logs: confirm `external_call` / `llm_call` entries now carry a
   real `cost_usd` (not null) **and** a non-null `session_id` even for the
   nested-thread DataForSEO calls (the `ContextThreadPoolExecutor` fix).
5. Re-run `/plan-articles` (or `/regate`) on the session and confirm
   `actual_cost_usd` **increases** (cumulative real spend) and the
   `article_planning`/`regate` phase in `cost_breakdown` grows — the documented
   cumulative behavior, not a bug.

**M10 live-validation checklist (deploy the branch first; Storage was unverifiable
in the sandbox):**

**M10 live-validation checklist (deploy the branch first; Storage was unverifiable
in the sandbox):**
1. As **owner** on a `complete` session, open the **Exports** tab → **Flat** →
   confirm a CSV downloads, opens, and matches the Table View (keyword, topic,
   cluster, source, relevance, status; Volume/KD/CPC blank). A row appears under
   "Past exports".
2. **Topic-grouped** → confirm a `.zip` downloads with one CSV per topic.
3. **Architecture** → on a session *with* a generated architecture, confirm one
   row per pillar + supporting article (`page_type, title, target_keyword,
   parent_pillar, outline_h2s, internal_links_out`); on a session *without* one,
   the button is disabled (and `POST …/export?format=architecture` → 400).
4. **Re-download** a past export → a fresh signed URL serves the same file.
5. **CSV injection:** seed/keyword data that starts with `=`/`+`/`-`/`@` renders
   as literal text (leading `'`) in the downloaded CSV.
6. As a **VA**: the Exports tab is present, export of *their own* session works,
   and `GET /sessions/{other-VA-session}/exports` / `POST …/export` → 404 (RLS),
   and they only see their own rows in the list.
7. Confirm `.storage.from_("csv-snapshots").upload(...)` + `.create_signed_url(...)`
   actually work on the service client (the one risk the sandbox couldn't test) —
   if storage3's response key or upload signature differs, adjust
   `backend/app/storage/exports.py` (the only deploy-only module).

**Still pending from earlier milestones (sandbox egress):** validate M9's approval
round-trip and M8's VA/owner routing on the live stack. For M9: (a) as a **VA**, configure an over-cap run (e.g. comprehensive + deep-mine 2 silos, or bump silos high) → the CostStep shows **Submit for approval**, not Run now; click it → the wizard lands on **Waiting for approval** and the session is `pending_approval`; (b) as the **owner**, the topbar **Approvals** badge shows the pending count, the `/approvals` page lists the request, and the decision modal **Approve & run** flips the session to `running` + kicks `/expand` (VA's waiting screen transitions to progress within 30s); (c) **Reject** with a note → the VA's waiting screen shows the note + Adjust & resubmit; (d) a **Cancel request** from the VA returns to the deep-mine step; (e) confirm an *under-cap* VA run still shows **Run now** and runs directly (no approval); (f) hit `GET /approvals`, `POST /sessions/{id}/approve|reject` with a **VA** JWT → 403. **Also still validate M8** (not browser-tested): VA vs owner routing via `/me`, the full VA wizard flow, the restricted results surface, and the owner-only 403s. Then start **M11 (cost + observability, §16)** — stop for a human go-ahead before building (milestone discipline). Carried flags to decide when they next block: metrics enrichment §7.8 (the VA metrics toggle is decorative, and the M9 estimate honestly omits metrics cost since the flag is false), `POST /projects` ("+ New project"), per-topic orchestrator re-run, session duplicate, server-side expand→plan chaining + a VA session-resume surface (so an owner-approved run completes even if the VA's browser is closed).

**Owner-only endpoints (M8, enforce server-side via `require_owner`):** cluster delete/merge/split/promote-primary, `coverage-gaps` accept/dismiss, `POST /architecture`, `DELETE /sessions/{id}`, `/regate`, `/cluster-preview`, `/routing-diagnostic`, `/lever3-simulate`, `/fanout`. A VA gets 403 at the dependency layer (before any DB work). The calibration tools (`/regate` etc.) the M5/M6 console workflow used are now owner-only — fine, since calibration is an owner task, but note it if a VA token is ever used for tuning.

**Settled in M7:** the **orchestrator-vs-direct planner default → orchestrator stays default** (it already was the code default; `direct` remains the opt-in `{"direct": true}` flag, so no code change). M7's "Re-run orchestrator" button uses the orchestrator. Note `4ecefaa1` itself was planned in *direct* mode (315 articles), so re-running it from the UI would consolidate to fewer orchestrator articles — expected.

**M7 carried/deferred (flagged, not blocking):** per-topic orchestrator re-run (only whole-session wired); split option (b) (re-run-on-article); session **duplicate** (§9.4); **metrics enrichment §7.8** still unbuilt so Table View Volume/KD/CPC are "—"; Table cluster-filter is single-select; keyword move uses a select (no drag-drop).

**Calibration workflow that emerged in M5** (reuse it): tuning is done against the **deployed API via browser-console `fetch`** (sandbox has no egress), and results are inspected via the **Supabase MCP tools**, not the UI (no session resume until M7). `/regate` re-runs gate+cluster on the *stored* pool (no DataForSEO) at an overridden threshold / edge / resolution / aliases / peer_entities — the cheap iteration loop. `/cluster-preview` and `/lever3-simulate` are read-only analysis.

**After M11 validation completes and merges to `main`, the M1–M11 build sequence is done.** Post-M11 design captured in **§8** (broader "produce a live site" plan) and **§9** (the now-current Writer-module integration direction — 2026-06-09; supersedes §8.5 #1; M12/M13 sketch in §9.10). Both planning-only — nothing built.

## 3. Deploy & infra state (CRITICAL — caused most of the pain this session)

- **`main` is the single deploy branch** for both Railway and Netlify. Milestones are built on `m{N}-...` branches and **merged to `main` (`--no-ff`)** when validated. Do NOT expect deploys from feature branches.
- **Railway** service `info-site-kw-research-cluster` (project `AR Tools`): **Root Directory = `backend`**, Dockerfile build, deploy branch `main`. Public URL **`https://info-site-kw-research-cluster-production.up.railway.app`**. `railway.json` has no `startCommand` (Dockerfile CMD owns port binding). `/healthz` returns the running commit via `RAILWAY_GIT_COMMIT_SHA` — use it to confirm a deploy landed before calibrating.
- **Netlify** site `kw-research-module` (id `dc24cc19-d745-4074-8967-e037f3c5e86a`): base dir `frontend/`, production branch `main`. Env vars set: `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.
- **Supabase** project = **AR-Internal-Tools**, ref **`wvcthtmmcmhkybcesirb`**, URL `https://wvcthtmmcmhkybcesirb.supabase.co`. Accessible via the Supabase MCP tools (apply_migration / execute_sql / get_logs). The `fanout` schema is **exposed in PostgREST** (Settings → API → Exposed schemas) — required, was a manual step.
- **Storage (M10):** private bucket **`csv-snapshots`** created via MCP (`insert into storage.buckets … public=false`). The backend's **service-role** client uploads + mints signed URLs (bypasses storage RLS), so no `storage.objects` policies are needed (the frontend only ever sees signed URLs). This bucket lives in the **shared** AR Tools project alongside `article-assets` / `files` / `wordpress_images` — don't touch those. **The sandbox cannot reach Storage**, so M10's upload + signed-URL path is validated only on the deployed stack.
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
- `api/` — `health.py`, `projects.py`, `sessions.py`, **`exports.py` (M10)**. Session endpoints: silo discovery, `/finalize`, `/deep-mine`, `/expand` (async), `/plan-articles` (async; body `{"direct": true}` skips the orchestrator), `/regate` (async; body overrides threshold/edge/resolution/aliases/peer_entities), `/fanout` (async; RF §7.7 — cost-gated, `{"confirm_cost": true}` to spend, optional resolution/threshold overrides), `/summary` (poll), `/clusters` (read), `/cluster-preview`, `/routing-diagnostic`, `/lever3-simulate` (read-only analysis), **`/debug` (M11, owner-only — `statistical_clustering_log` + `orchestrator_log` + cost, §15.3 #8)**. **`exports.py` (§12):** `POST /sessions/{id}/export?format=flat|topic_grouped|architecture` (sync — generate + snapshot + record + signed URL), `GET /sessions/{id}/exports` (the Exports tab list), `GET /exports/{id}/download` (re-sign a fresh URL). All `require_user`, both roles, RLS-scoped.
- `csv_export.py` (**M10**, PRD §12) — **pure** CSV builders (`build_flat_csv`, `build_topic_grouped_csvs` + `zip_named_csvs`, `build_architecture_csv`) over already-fetched rows + CSV formula-injection hardening (`_safe`). No egress; all of M10's correctness coverage is here (`tests/test_csv_export.py`). The Storage upload + signed-URL layer is `storage/exports.py` (deploy-only).
- `auth/dependencies.py` — `require_user` (verifies Supabase JWT via service client; logs real reason on failure). **M8:** `get_role(user)` (reads `user_profiles.role`) + `require_owner` dependency (403 for non-owners) for the §11.2 capability gates.
- `cost.py` (**M9**, PRD §8.1/§8.4) — pure `estimate_cost(...)` (per-component §8.1-derived rates → total + breakdown, recursive ×5) + `requires_approval(...)` (estimate > soft cap OR recursive). No egress; unit-tested in `tests/test_cost.py`. The approval endpoints (`/cost-estimate`, `/submit-for-approval`, `/cancel-approval`, `/approvals`, `/approve`, `/reject`) live in `api/sessions.py`; storage helpers `get_workspace_settings` / `count_gated_topics` / `list_pending_approvals` + the `/summary` `approval` block in `storage/silo.py`.
- `cost_meter.py` (**M11**, PRD §16.4) — the live **actual**-cost machinery (vs. `cost.py`'s estimate). `CostMeter` (thread-safe, per-run, broken down by pipeline phase) + the `_meter`/`_step` contextvars + `record_cost(cost)` (called from the four external-API clients) + the LLM/embedding `$`-per-token rate table (`llm_token_cost` / `embedding_token_cost` — **estimates**, calibrate per §8.1). DataForSEO cost is the **real** per-call charge from its task envelope. No egress; unit-tested in `tests/test_cost_meter.py`.
- `cost_attribution.py` (**M11**) — bridges the meter to storage: `metered_run(session_id, step)` (background-job context manager: binds the meter on the job thread, periodic + final lock-serialized flush of `actual_cost_usd` + `cost_breakdown`, cumulative onto the existing total) and `metered_sync(session_id, step)` (single final flush, for the synchronous silo-discovery call). `jobs.py` applies a `@_metered("…")` decorator to each job; `api/sessions.py` wraps silo discovery in `metered_sync`.
- `concurrency.py` (**M11**) — `ContextThreadPoolExecutor`: a `ThreadPoolExecutor` whose `submit` runs each task inside a `copy_context()` snapshot, so the meter + `session_id`/`correlation_id` propagate into the pipeline's nested API-call worker threads. Imported under the `ThreadPoolExecutor` alias by `expansion.py` / `competitor.py` / `serp.py` / `orchestrate_articles.py` / `architecture/generate.py`.
- `storage/supabase_client.py` — service client (RLS-bypass, admin writes) + user client (anon key + user JWT, RLS-enforced reads). `storage/silo.py` — session/topic/keyword/cluster DB ops incl. `set_topics_gating`, `get_topic_embeddings`, `insert_classified_keywords`, `try_mark_running`, `get_session`, `list_all_keyword_pool` (re-gate pool reconstruction), `persist_article_plan` (staged cluster write), `reset_article_planning`, `get_pipeline_summary`, `list_clusters`, **`list_surviving_keywords` (M10, paged active/excluded/covered pool for export)**, **`get_session_cost` / `flush_session_cost` / `get_session_debug` (M11)**. The `/summary` payload now also carries a live `cost` block (`estimated_cost_usd`/`actual_cost_usd`/`breakdown`) in both the cheap-running and full paths. `storage/exports.py` (**M10**) — Supabase **Storage** ops (`upload_snapshot` to the `csv-snapshots` bucket via the service client, `create_signed_url`) + `csv_exports` table ops (`insert_export` [service], `list_exports` / `get_export_visible` [user client, RLS]). **Deploy-only** (sandbox can't reach Storage).
- `llm/openai_client.py` — GPT-5.4 grounding + silo proposal (Responses API + web_search) + `embed()`.
- `dataforseo/client.py` — DataForSEO calls (demand sample, SERP structure, expansion endpoints, autocomplete; M4: `serp_top_urls`, `ranked_keywords`, `domain_of`).
- `pipeline/` — `silo_discovery.py` (M2), `expansion.py` (M3), `competitor.py`/`relevance.py`/`clustering.py` (M4), `orchestrate.py` (M4 `run_refinement_pipeline` + M5 `gate_and_cluster`/`cluster_preview`/`routing_diagnostic`/`simulate_best_silo_clustering`), `models.py`.
- `pipeline/article_planning/` (M5) — `orchestrate_articles.py` (chunked orchestrator + `direct` mode), `dedup.py`, `serp.py`, `models.py`. `jobs.py` (M5) — async background worker (M6/RF: `run_fanout_job`). `llm/anthropic_client.py` — Opus 4.7 tool-use client. `relevance.py` now also does the peer-entity filter + Lever-3 routing.
- `pipeline/recursive_fanout.py` (RF §7.7) — `derive_sub_anchors` (top-N cluster reps per silo), `run_recursive_expansion` (reuses `run_expansion`, remaps synthetic sub-anchor topics back to parent silos, tags `recursive`), `merge_into_pool`. Drives `run_fanout_job`.
- `pipeline/architecture/` (M6 §7.11) — `models.py` (`PillarInput`/`ArticleInput` in, `Pillar`/`SupportingArticle`/`ArchitectureResult` out; `architecture_json()` = the stored shape, `all_degraded()`), `generate.py` (`run_architecture_generation`: per-pillar Opus editorial call in parallel + deterministic `_lateral_pillar_links` [cosine > 0.55] / `_lateral_article_links` [peer-priority, centroid fill] + degraded stub). Reuses `get_orchestrator()` (the Anthropic client, §7.11). Drives `run_architecture_job` in `jobs.py`.

Frontend M9 additions: `owner/ApprovalsPage.tsx` (route `/approvals`, owner-only) — the approval queue + a decision modal (approve/reject + note), 30s poll. `shared/AppShell.tsx` gained an owner-only **Approvals** nav link with a pending-count badge (`enabled: isOwner`, 30s poll). `va/Wizard.tsx`: CostStep now fetches `getCostEstimate` and branches Run-now vs Submit-for-approval; new **WaitingStep** (polls `/summary`, cancel via `cancelApproval`, reject shows the note + adjust-&-resubmit); DeepMineStep shows a live server estimate. `shared/api.ts` gained `getCostEstimate` / `getWorkspaceSettings` / `submitForApproval` / `cancelApproval` / `listApprovals` / `approveSession` / `rejectSession` + the `approval` field on `PipelineSummary`. Query key `["approvals"]` (badge + page share it); `["cost-estimate", sessionId, gatedCount]`.

Frontend (M7/M8, react-router): `App.tsx` is **role-gated** — `RoleRoutes` reads `me.role` and renders `OwnerRoutes` (`/projects`, `/session/new`, `/session/:id/{table,cluster,architecture,split}`) or `VaRoutes` (`/wizard`, `/session/:id/{table,cluster,architecture}` — no split; everything else redirects to `/wizard`). On a `/me` failure it falls back to the more-restricted VA routes. `va/Wizard.tsx` (M8) is the 9-step VA wizard (reuses `shared/api.ts`; auto-chains expand→plan in the progress step). `SessionWorkspace`'s `SessionCtx` now carries `role`, which the shared views (`TableView`/`ClusterView`/`ArchitectureView`) read to hide owner-only controls for VAs. `owner/SiloDiscovery.tsx` is the creation+pipeline flow (seed → disambiguation → silo review → finalize → **deep-mine** → run → results), reached via `owner/NewSession.tsx`. `owner/ProjectsPage.tsx` = Project+Session Browser (§9.4) with archive/move/delete. `owner/SessionWorkspace.tsx` = per-session shell (segmented control + status gate) that passes a `{sessionId, topics, topicName}` context to `owner/views/{TableView,ClusterView,ArchitectureView,SplitView}.tsx`. `shared/AppShell.tsx` (topbar), `shared/sessionStatus.ts` (status labels + `hasResults`), `shared/api.ts` (all calls incl. M7b mutations), `shared/auth.tsx`, TanStack Query (query keys: `["clusters",id]`, `["keywords-all",id]` paged surviving pool, `["summary",id]`, `["architecture",id]`, `["sessions",projectId,showArchived]`). Views are read-only when the session lacks results; editing mutations invalidate `clusters`+`keywords-all`.

Schema migrations in `supabase/migrations/`: `..._fanout_initial.sql` (M1), `..._topics.sql` (M2), `..._keywords.sql` (M3), `..._keywords_relevance.sql` (M4), `...20260525000000_clusters.sql` (M5: `clusters` + `coverage_gaps` + orchestrator keyword cols + `awaiting_article_planning` status), `..._session_last_error.sql` (M5), `..._peer_entities.sql` (M5: `sessions.aliases` + `peer_entities`), `...20260526000000_site_architecture.sql` (M6: `site_architecture` table + RLS), `...20260527000000_session_archive.sql` (M7b: `sessions.archived`), `...20260528000000_csv_exports.sql` (**M10**: `csv_exports` table + the `csv_export_format` enum + real RLS via a `sessions`-join), `...20260529000000_session_cost_breakdown.sql` (**M11**: `sessions.cost_breakdown jsonb`; no RLS change). All applied to the live DB via Supabase MCP (the M7 column on 2026-05-26; the M10 table on 2026-05-28; the M11 column on 2026-05-29, verified — column present, RLS still enabled). **M9 added no migration** — the approval columns (`estimated_cost_usd`, `actual_cost_usd`, `approval_required`, `approval_decided_by_user_id`, `approval_decision_at`, `approval_note`) and the `pending_approval`/`rejected` statuses were created in the M1 `..._fanout_initial.sql` migration. The **`csv-snapshots` Storage bucket** (private) was also created via MCP for M10 (it's not a SQL migration; `insert into storage.buckets`).

Frontend M10 additions: `owner/views/ExportsView.tsx` (route `exports`, added to **both** the Owner + VA segmented controls in `SessionWorkspace`) — three format Download buttons (architecture disabled until the summary reports an architecture) + a "Past exports" list with per-row re-download; opens the backend-minted signed URL in a new tab. `shared/api.ts` gained `createExport` / `listExports` / `downloadExport` + the `CsvExport*` types. Query key `["exports", sessionId]` (new, no clash); reuses `["summary", sessionId]` to gate the architecture button. CSS: `.export-actions`.

Frontend M11 additions: `shared/CostBanner.tsx` (live actual-vs-estimate cost banner + progress bar; red when actual > estimate) rendered on the Owner `SessionWorkspace` head and the VA wizard `ProgressStep`; both read the new `cost` block on the `/summary` poll. `owner/DebugView.tsx` (route `/session/:id/debug`, **OwnerRoutes only**) — per-step cost table + raw `orchestrator_log` / `statistical_clustering_log`; reached via an owner-only "Debug" link in the workspace head. `shared/api.ts` gained `SummaryCost` (on `PipelineSummary`) + `SessionDebug` + `getSessionDebug`. Query key `["debug", sessionId]`. CSS: `.cost-banner*`, `.debug-link`, `.debug-table`, `.debug-json`.

## 6. Useful commands / queries

Backend (from `backend/`, venv at `.venv`):
```bash
. .venv/bin/activate
python -m pytest -q          # 176 tests, all passing
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

## 8. Post-M11 planning — site creation orchestrator

**Status: planning only, nothing built.** Captures the 2026-06-05 design conversation. Open decisions in §8.5 to resolve before drafting M12.

### 8.1 The shape

Extend this tool from "produces a content map" to "produces a live site." Stack: GitHub (one repo per site) + Cloudflare Pages (one project per site) + existing Supabase + Railway. **Two templates** — informational (no images, editorial design) and local SEO (**one site per business/location**, with images, schema.org `LocalBusiness`, NAP). Owner picks template at site-creation; data model is identical for both (one `fanout.sites` row, one repo, one CF Pages project per site).

### 8.2 Workflow

1. **Research** (M1–M11, already built) — seed → architecture → finalized in Owner UI.
2. **Site setup** (new) — owner picks template + domain + brand/business config. Orchestrator provisions GitHub repo + CF Pages project + domain attach via APIs. Persists to `fanout.sites`.
3. **Content orchestration** (new) — orchestrator inserts one work row per planned page; an existing writer service claims it, produces HTML, pushes to the repo. Async, server-side (mirrors M5 `app/jobs.py`).
4. **Review** (optional, new) — owner inspects drafts before publish (per-article or per-silo).
5. **Publish** (new) — CF Pages auto-builds on push; deploy status streams to the Owner UI.

Postgres = source of truth for content; the repo is regenerated from it. "Regenerate one article" is trivial (no git surgery); "edit repo directly and have it flow back" doesn't work — acceptable for this use case.

### 8.3 Decisions made (2026-06-05 conversation)

- **Coordination = shared Postgres queue (Option C).** Orchestrator inserts work rows, writer claims via `SELECT … FOR UPDATE SKIP LOCKED`, updates status when done. Restart-tolerant on both sides; status visibility is free (Owner UI reads the same rows). No HTTP between services. Mirrors `app/jobs.py`. (Considered: sync HTTP — fragile to Railway's 5-min edge cap; async HTTP + webhook — more wiring; Redis — overkill for hundreds of jobs.)
- **One repo + one CF Pages project per site** — sites portable as standalone assets; scales to hundreds (reassess at thousands).
- **Internal links via registry table + republish fan-out** — pages publish incrementally, so the writer can't render links to targets that don't exist yet. Writer emits placeholders; orchestrator resolves at publish time against a live `internal_links` table. When a new page publishes, already-published referrers get their links re-resolved and re-pushed.
- **Two-pass content generation is the cost sweet spot** — Haiku draft for all articles + Opus rewrite for pillars only. ~$9/site for ~300 articles vs. ~$38 all-Opus or ~$8 all-Haiku. Easy to flip per-site.
- **Cost reference** (per ~3000-word article, 1.5K input / 4.5K output, current rates): Opus 4.8 ~12¢, Sonnet 4.6 ~7¢, Haiku 4.5 ~2.5¢.

### 8.4 Writer landscape (discovered via MCP probing 2026-06-05)

Three apps could serve as the content writer:

- **ShowUP Local** (Railway service `showup-local` in project `ShowUP Local`, Supabase project `ShowUp` ref `yvdfiwabdvcpqwrmtysd`) — production local-SEO writer. Schema: `business_profiles` (GBP data, hours, brand voice, ICP) + `keyword_analyses` (SERP/competitor research per kw) + `generated_pages` (`mode` ∈ generate/reoptimize/audit, scoring, `content_html`/`schema_json` outputs). **Synchronous (no queue), no repo push** — output lives in `generated_pages.content_html`. Full SaaS scaffolding (credits, users, notifications, press releases). 7 business profiles, 24 generated pages, 17 keyword analyses.
- **Kyle The SEO GOAT** (Railway service `kyletheseogoat` in project `eloquent-integrity`, Supabase project `Kyle The SEO GOAT` ref `txcwedbyyneeqtfidtyo`) — byte-identical schema clone of ShowUP Local, **all tables empty, unused.** Looks like a whitelabel/staging instance never repurposed.
- **AR-Internal-Tools `public` schema** (same Supabase as this app, ref `wvcthtmmcmhkybcesirb`) — **the real find.** Multi-module content production pipeline:
  - `clients` (multi-tenant brand profiles with brand guide, ICP, GBP, GSC property, Google Drive folder)
  - `runs` (per-keyword runs; status flows `queued → brief_running → sie_running → research_running → writer_running → sources_cited_running → complete`)
  - `module_outputs` (5 modules per run: brief / sie / research / **writer** / sources_cited; with attempt tracking, cost, duration)
  - `client_context_snapshots` (frozen client context per run)
  - `async_jobs` (generic queue with retry/backoff; currently used for `website_scrape` + `silo_dedup`)
  - `briefs_cache` + `sie_cache` (cross-client caches keyed by keyword+location_code)
  - `silo_candidates` with pgvector embeddings + status `proposed|approved|rejected|in_progress|published|superseded` — **this app already does silo planning too** (conceptual overlap with `info-site-kw-research-cluster`)
  - `local_seo_pages` (empty/scaffolded — an unbuilt port of ShowUP Local's `generated_pages` into AR-Internal-Tools)

**Recommended mapping (subject to §8.5 decisions):**
- **Informational template → AR-Internal-Tools `runs` pipeline.** Research-backed, source-cited, brief-driven — exactly what an authority site wants. Orchestrator inserts one `public.runs` row per planned article (with `client_id` = the AR-Internal-Tools `clients` row representing the site). Same Supabase as the orchestrator → no cross-DB coordination.
- **Local SEO** — two paths: (a) keep ShowUP Local on its separate Supabase (cross-Supabase, HTTP coordination, ships faster); (b) port into AR-Internal-Tools `local_seo_pages` (single-Supabase, queue coordination, cleaner long-term).

### 8.5 Open decisions (resolve before drafting M12)

1. **Informational writer:** use AR-Internal-Tools `runs` pipeline, or build a duplicated standalone writer? AR-Internal-Tools = deeper app-to-app coupling but skips duplication + yields higher-quality writer (research + sources cited out of the gate).
2. **Local SEO writer:** keep ShowUP Local (cross-Supabase, HTTP coordination) or port into AR-Internal-Tools `local_seo_pages` (single-Supabase, queue coordination)?
3. **H2 outline preservation:** ~~pass M5/M6 H2 outlines as constraints to the `brief` module, or let it produce its own outline from scratch?~~ **RESOLVED 2026-06-09: the writer owns H2 generation; the pipeline no longer produces outlines.** Commit `67c1c2c` dropped H2 generation from both the M5 orchestrator (`suggested_h2s`) and the M6 architect (`h2_outline`) — schema + prompt removed, every article/pillar persisted with an empty outline. The `clusters.h2_outline` column + the model fields are kept (always empty) as the destination the writer fills at write time. The §9.2 adapter therefore does **not** pass a `heading_structure` from the pipeline — the writer generates it. Consequence until M12+ ships: Architecture view + architecture CSV `outline_h2s` are blank. Flagged divergence from PRD §7.10/§7.11.
4. **Repo + CF Pages provisioning:** orchestrator owns it (recommended; provisions at site-create time), or owner provisions manually (faster to ship the first version)?
5. **Owner review step:** required before publish (safer; recommended), or auto-publish on generation complete (faster; per-site toggle later)?
6. **One writer with template modes vs. two writers per template** — depends on how much the two templates' generation pipelines actually share. Currently leaning two (different shape: local SEO needs business context + schema.org + images; informational needs internal-linking-heavy editorial with no images).
7. **Strip duplicate writer of SaaS scaffolding** (credits/users/notifications/press releases) — only relevant if #1 goes the "duplicate" route.

### 8.6 Outstanding integration contract details (if using AR-Internal-Tools)

- **`runs` input mapping:** AR-Internal-Tools takes `keyword + intent_override + sie_outlier_mode`. The M5/M6 H2 outline has no obvious slot — it would either go into the brief module's input (overriding/guiding) or be discarded. See decision #3.
- **Repo push step:** AR-Internal-Tools doesn't push to a repo today. Two options: (a) add a 6th module (extends `runs.status` with `publishing → published` tail), or (b) do it in this orchestrator (reads completed `module_outputs`, formats HTML, pushes). **Recommendation: orchestrator owns it** — keeps AR-Internal-Tools focused on content, keeps GitHub credentials in one service.
- **`clients` per site:** orchestrator creates one AR-Internal-Tools `client` per `fanout.sites` (or reuses for whitelabel scenarios).
- **Internal-link awareness:** AR-Internal-Tools' writer doesn't know about sibling articles — either it emits placeholders the orchestrator resolves at publish time, or the orchestrator does a post-write link-injection pass on the writer's HTML output.

### 8.7 Security finding (address before M12 ships)

**`AR-Internal-Tools.public.sie_cache` has RLS DISABLED** while every other table in that schema has it on. With Supabase's anon key, anyone could read or modify the SIE cache. Remediation:
```sql
ALTER TABLE public.sie_cache ENABLE ROW LEVEL SECURITY;
```
**Don't run blind** — enabling RLS without policies will break the writer service's reads. Add a service-role-only policy (or whatever pattern AR-Internal-Tools uses elsewhere) before flipping it on. Decide with the AR-Internal-Tools owner.

### 8.8 Likely M12 shape (once decisions land)

- **New `fanout` tables:** `sites` (id, name, template, repo_url, cf_project_id, domain, site_config jsonb, ar_client_id), `generation_jobs` (or use AR-Internal-Tools `runs` directly per decision #1), `internal_links` (from_slug, to_slug, anchor, status), `published_pages` (slug, status, commit_sha, published_at), `site_publishes` (per-push log). All under `fanout` schema with real RLS.
- **Backend:** site provisioning service (GitHub repo + CF Pages project + domain attach via APIs), dispatcher that materializes architecture → writer jobs, publish step (HTML → repo push), internal-link resolver + republish fan-out, retry/status endpoints.
- **Frontend:** "Create site from session" action on the workspace, sites list, generation progress dashboard (reads queue rows directly), optional review tab, publish status.
- **Writer-side:** depends on decision #1. If using AR-Internal-Tools: no writer changes beyond the orchestrator's `runs`-row insertion (plus a contract doc describing the input/output shapes). If duplicating: duplicate needs a queue worker + repo push + simplification of SaaS scaffolding.

## 9. Blog Writer module integration plan (post-M11, 2026-06-09)

**Status: design captured, nothing built.** From the 2026-06-09 conversation
reviewing the AR Tools Blog Writer PRD bundle (8 PRDs: Writer / Brief Generator
/ SIE / Research & Citations / Sources Cited / Content Quality / Suite
Architecture / Engineering Spec). **Narrower than §8** — §9 generates *article
prose* per planned architecture article into `fanout.article_outputs`; §8's
GitHub / CF Pages publish layer would sit on top of it. Implicitly shifts
§8.5 #1 from "use AR-Internal-Tools `runs` pipeline" to a **third option**:
port only the Writer module into this repo in degraded mode (no cross-Supabase
coupling, no full duplicate).

### 9.1 Scope (v1)

Port the **Writer module** (PRD #1, v1.7) into `backend/app/writer/` as an
in-process Python package. **Skip** the other 4 modules. Degraded mode:
- `schema_version_effective: "1.7-no-context"` — no brand voice / ICP / client
  context (skip Steps 3.5a / 3.5b / 3.6 / 3.8 — distillation, reconciliation,
  placement plan, ICP-callout judge).
- `no_citations: true` — no Research module, no `{{cit_N}}` markers, no Sources
  Cited renderer (skip Step 4F + the §5.8.8 citable-claim retries).

Writer invariants we **keep**: topic-adherence filter, paragraph-length cap,
per-H2 body-length floor, key takeaways, Agree/Promise/Preview intro, CTA,
banned-term regex (no-op with empty list), title-case pass, MD + HTML
serialization.

Cost: ~$0.20–$0.40/article. Time: ~30–45s. **No new third-party deps** (no
Google NLP, no ScrapeOwl, no client/brand layer). Provider unchanged
(Anthropic — Sonnet for prose, Haiku for short/classification per the PRD's
Call Inventory §17).

### 9.2 Adapter (cluster → Writer input)

`backend/app/writer/adapter.py`, pure function
`build_writer_payload(cluster_id) → (brief, sie_stub)`. Synthesizes the
Writer's required inputs from existing data:

| Writer field | Source in this repo |
|---|---|
| `brief.keyword` | `clusters.primary_keyword.text` |
| `brief.title` | One Haiku tool-use call (cached on `clusters.adapter_cache`) |
| `brief.scope_statement` | Derived from `clusters.intent` + name |
| `brief.intent_type` | One Haiku classification call (8 enums; cached) |
| `brief.heading_structure[]` | H1 + parsed H2s from `clusters.h2_outline` + faq-header + N faq-questions + conclusion |
| `brief.faqs[]` | One Sonnet tool-use call (3–5 FAQs; cached) |
| `brief.format_directives` | Static lookup keyed by `intent_type` (mirrors Brief Gen v2.3 `intent_format_template`) |
| `brief.metadata.word_budget` | 2,500 default |
| `sie.terms.required[]` | Cluster's supporting keywords as flat list (no zone targets, no `is_entity`) |
| `sie.target_keyword.minimum_usage` | `{h2: 1, h3: 0, paragraphs: 6}` |
| `research.citations[]` | `[]` (Writer flips `no_citations: true`) |
| `client_context` | omitted |

Three LLM calls per cluster (title + intent + FAQs), all cached on
`clusters.adapter_cache` → amortized to ~$0 per re-run.

### 9.3 Schema additions (all in `fanout` schema, real RLS)

```sql
-- migration 2026...._writer_integration.sql

alter table fanout.sessions add column site_base_url text;
alter table fanout.clusters add column slug text;
alter table fanout.clusters add column adapter_cache jsonb;
create unique index on fanout.clusters (session_id, slug);

create table fanout.content_schedules (
  id            uuid primary key default gen_random_uuid(),
  session_id    uuid not null references fanout.sessions(id) on delete cascade,
  mode          text not null check (mode in ('all_at_once','drip')),
  per_day       int,            -- null for all_at_once; >=1 for drip
  start_date    date,
  time_of_day   time not null default '09:00',
  timezone      text not null default 'UTC',
  status        text not null default 'active'
                check (status in ('active','paused','complete','cancelled')),
  total_count   int not null,
  user_id       uuid not null,
  created_at    timestamptz not null default now()
);

create table fanout.scheduled_article_runs (
  id                    uuid primary key default gen_random_uuid(),
  content_schedule_id   uuid references fanout.content_schedules(id) on delete cascade,
  cluster_id            uuid not null references fanout.clusters(id) on delete cascade,
  session_id            uuid not null references fanout.sessions(id) on delete cascade,
  scheduled_at          timestamptz not null,
  status                text not null default 'queued'
                          check (status in ('queued','running','complete','failed','cancelled')),
  user_id               uuid not null,
  started_at            timestamptz,
  completed_at          timestamptz,
  error                 text,
  created_at            timestamptz not null default now()
);
create index on fanout.scheduled_article_runs (status, scheduled_at)
  where status = 'queued';

create table fanout.article_outputs (
  id                          uuid primary key default gen_random_uuid(),
  cluster_id                  uuid not null references fanout.clusters(id) on delete cascade,
  scheduled_article_run_id    uuid references fanout.scheduled_article_runs(id) on delete set null,
  article_json                jsonb not null,
  article_markdown            text not null,
  article_html                text not null,
  total_word_count            int,
  cost_usd                    numeric(10,4),
  schema_version_effective    text not null,
  generated_at                timestamptz not null default now()
);
create index on fanout.article_outputs (cluster_id, generated_at desc);
```

RLS: owner = all; VA = via session ownership (mirrors M7/M8 keyword +
architecture policies). Never `using (true)`.

### 9.4 Bulk scheduling — all-at-once OR drip N/day

**`Schedule all`** modal on the Architecture view:
- **Whole-session scope** (not subset — kept simple).
- Mode toggle: **All at once** or **Drip N/day**.
- Drip fields: per-day, start date (≤ 365d out), time of day.
- **Every calendar day** (no weekend skip).
- **Required:** `Site base URL` — modal blocks if empty (absolute URLs, §9.5).
- Live preview: *"315 articles · 5/day · finishes Aug 18, 2026 (63 days)."*
- Cost preview: `count × ~$0.30`.

`backend/app/writer/schedule_planner.py` (pure):
1. Order all session clusters **pillars first**, then by architecture order
   (stable, deterministic).
2. all-at-once: every run `scheduled_at = now()`.
3. drip: `scheduled_at(i) = start_date + floor(i / per_day) days @ time_of_day` in `timezone`.
4. Validate `ceil(count / per_day) ≤ 365` — else 400 with `min_per_day` hint.
5. Materialize the parent `content_schedules` row + N children in **one transaction**.

Pillars-first guarantees a supporting article never generates before its
pillar — its up-link resolves on day 1.

### 9.5 Internal linking (deterministic injection)

Writer PRD §1.3 explicitly excludes internal linking. M6 already computed the
link graph in `site_architecture.architecture_json` (pillars + supporting +
lateral, no orphans, no dangling). The integration **deterministically injects**
the links — same philosophy as M6 ("LLM writes the prose, code wires the
graph"), same contract pattern as `{{cit_N}}`.

**Slugs assigned at plan time:** every cluster gets a stable `slug`
(deterministic from primary keyword/title, deduped within session). So article A
generated on day 1 can link to article B scheduled for day 40 — B's URL is
knowable from B's slug + session base URL before B exists. **Drip-safe by
construction.**

**Absolute URL form:**
- Pillar: `{base_url}/{silo-slug}/`
- Supporting article: `{base_url}/{silo-slug}/{article-slug}`

**`backend/app/writer/link_injector.py`** runs after Writer returns, **before**
Step 10 serialization:
1. Read targets from `architecture_json` (up + lateral for supporting; down for
   pillars).
2. For each target, find first prose occurrence of its primary keyword (then
   supporting kw, then title tokens) — skipping headings, existing links, code
   spans — and wrap as `[match](absolute URL)`. One link per target, one wrap.
3. **Pillars** render an "In this guide" structured list of all children
   (don't inline 60 links).
4. **Fallback:** unmatched targets drop into a **"Related articles"** list
   before the conclusion — guarantees the M6 link contract regardless of prose.
5. Re-serialize → `article_markdown` / `article_html` carry resolvable
   absolute internal links.

**Link-health report** at batch end: flags any link whose target was
cancelled/failed (dangling).

### 9.6 Worker (cron mechanism)

**In-process asyncio loop** in the existing FastAPI backend (CLAUDE.md
scheduler-confirmation requirement met). Matches the M5 `app/jobs.py` pattern;
no new Railway service, no Postgres extensions enabled on shared Supabase, no
new infra. Trade-off: heartbeat lives in the web process — but durable rows
mean a restart catches up on the next tick, and the **startup recovery sweep**
resets stuck `running` rows older than a timeout (closes the M5-flagged
durable-queue gap on this path).

Every ~60s:
```sql
update fanout.scheduled_article_runs
   set status='running', started_at=now()
 where id in (
   select id from fanout.scheduled_article_runs
    where status='queued' and scheduled_at <= now()
    order by scheduled_at
    limit (CAP - currently_running)
    for update skip locked     -- two heartbeats / replicas never grab same row
 )
returning *;
```

For each claimed row → adapter → Writer (degraded) → `link_injector` →
persist `article_outputs` → flush cost via M11's `CostMeter` under a new
`article_generation` phase.

Concurrency cap: **3 in-flight** (LLM rate-limit guard). So "all at once" on
315 articles = "as fast as cap + rate limits allow," not 315 parallel calls.

### 9.7 UI surface

- **Architecture view** (existing) gains a session-level **`Schedule all`**
  button → modal (§9.4). Per-article **`Schedule`** / **`Generate now`**
  controls for one-offs.
- **Article view** (new, `/session/:id/article/:cluster_id`): latest
  `article_outputs.article_markdown` (MD / HTML / JSON toggle), cost,
  generation timestamp, owner-only **`Regenerate now`**.
- **Schedule overview** (new, `/schedule` for owner; per-session for VA):
  table of all scheduled + recent runs (cluster, project, `scheduled_at`,
  status, cost). Per-batch row above (mode, progress "14 / 315 done", next
  run, pause/cancel). Link-health indicator.
- **App-shell badge** (owner-only, 30s poll): "due in next 24h" + "failed in
  last 24h" counts.

### 9.8 Workflow summary (end-to-end)

1. **Plan** (M1–M11): seed → silos → clusters (articles with H2 outline + kw) →
   architecture (pillars + linking graph) — unchanged.
2. **Pre-schedule** (new, one-time per session): assign `clusters.slug` for
   every article, set `sessions.site_base_url` in the modal.
3. **Schedule** (new): `Schedule all` → planner materializes
   `content_schedules` + N `scheduled_article_runs` rows.
4. **Worker drains** (new): asyncio loop claims due rows up to the cap;
   adapter → Writer → link injector → `article_outputs`. Pillars first, so
   children's up-links always resolve.
5. **Review** (new): Article view / Schedule overview. Owner can regenerate or
   pause/cancel the batch. Link-health report flags dangling targets.

### 9.9 Open decisions (resolve before drafting M12)

1. **Concurrency cap default** (3?) — fine-tune against Anthropic rate limits
   on first live run.
2. **Re-plan cascade** — M5/M7's `reset_article_planning` deletes clusters →
   FK cascade drops pending schedules. UI should warn before re-plan;
   alternative is to re-target by `cluster.name` match (more complex).
3. **Dangling-link policy** when a child article is cancelled/failed —
   leave + report (default), auto-prune, or block.
4. **VA scope** — can a VA schedule + view articles, or owner-only? Wizard
   surface implications.
5. **Anthropic model tier for Writer section calls** — PRD §17 locks Sonnet;
   this repo's M5/M6 orchestrator uses Opus 4.7. Confirm: Sonnet for
   cost/budget vs. Opus on pillars only (cf. §8.3 "two-pass" cost note).

### 9.10 Likely milestone sequence

- **M12 — Writer foundation:** port Writer module + adapter + degraded-mode
  contract; manual **`Generate now`** button (owner-only) on the Architecture
  view. No scheduling, no link injection yet. Validates the Writer contract
  on real clusters; cost + quality observed before scheduling logic.
- **M13 — Scheduling + internal linking:** asyncio worker loop, **`Schedule
  all`** modal (all-at-once + drip), `link_injector`, article view, schedule
  overview, link-health report.
- **M14 (optional) — Brand voice + citations:** add `fanout.clients` layer +
  bolt in Research module + Sources Cited renderer. Deferred until v1 quality
  is judged insufficient.

### 9.11 Locked decisions (2026-06-09)

| Topic | Decision |
|---|---|
| Integration depth | **Writer + adapter only.** Skip Brief Generator, SIE, Research, Sources Cited. |
| Brand voice | **Skip in v1** (`1.7-no-context`). `clients` layer deferred to v2 (M14). |
| Citations | **Skip in v1** (`no_citations: true`). Research module bolted on later without schema changes. |
| Cadence semantics | **Per-article one-shot publish date.** Recurring refresh deferred. |
| Bulk mode | **All-at-once** OR **drip N/day**, whole-session scope, ≤365d horizon. |
| Drip order | **Pillars first**, then architecture order. |
| Drip days | **Every calendar day** (no weekend skip). |
| Internal-link anchors | **Deterministic injection** (code-finds keyword + wraps; "Related articles" fallback). |
| Internal-link URLs | **Absolute** (`sessions.site_base_url` required to schedule). |
| Cron mechanism | **In-process asyncio loop** (matches M5 `app/jobs.py`). |

### 9.12 Relationship to §8

§8 is the broader "produce a live site" plan (GitHub repo + CF Pages + domain
attach). §9 is the **content generation layer** §8 needs. The §8.5 #1
decision ("informational writer: AR-Internal-Tools `runs` pipeline vs full
duplicate") shifts to a **third option** — port only the Writer module from
the AR Tools Blog Writer bundle into this repo, in degraded mode. No
cross-Supabase coupling, no AR-Internal-Tools `runs` dependency. The §8.4
writer-landscape findings remain useful context but the chosen path is
neither of the two paths §8.5 #1 originally framed.

If §8's publish layer ships later, it reads `fanout.article_outputs`
(Markdown + HTML already serialized + internally linked) and pushes them
into the repo. No further generation step required.
