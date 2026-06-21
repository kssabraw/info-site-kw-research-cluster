# Handoff — Topic Fanout Tool build

This is a session-continuity doc. **Read `CLAUDE.md` and `docs/topic-fanout-prd-v1_7.md` first** — they hold the locked decisions and the spec. This file captures live state, the immediate next action, and hard-won gotchas not in those docs.

> **▶ Resume here (dead-simple):** the immediate next action is the **M12 (SIE)
> live-validation** — M12 is **code-complete, merged to `main`, and DEPLOYED**
> (2026-06-21; Railway `46ea998a` SUCCESS), and its `keyword_analyses` migration is
> applied to prod. **What's left for M12 is the owner running ONE live Term-analysis**
> on a real cluster keyword (Owner → Cluster view → expand an article → **Term
> analysis**; ~1–3 min, ~$0.30–$0.60) — the first real egress run, so expect minor
> first-run calibration on the ScrapeOwl/TextRazor response shapes + the Haiku/Sonnet
> tool schemas. **Then stop for review; M13 (Brief Generator, answer-engine-first —
> `docs/aio-optimization-plan.md`) is next.** See the 2026-06-21 dated entry for the
> full M12 build. (Older standing item, lower priority: the **M11 / M8–M10
> live-validation checklist** in §2 — deployed-stack browser/DB checks; nothing
> mid-flight.)
>
> **Post-v1 sequence (owner, 2026-06-12): M12 = SIE ✅ deployed (validation pending)
> → M13 = Brief Generator (`docs/brief-generator-module-plan.md` + the
> answer-engine-first pivot in `docs/aio-optimization-plan.md`) → M14 = Writer
> (`docs/writer-module-plan.md`) → M15 = scheduling + link injection.**
> Both Brief Gen and SIE run lazily at write time only (parallel stage 1 of
> `run_article_job`) — never during keyword research.** The AR Tools Blog Writer bundle is in
> the repo (`docs/blog-writer-pipeline-bundle.md`, all 8 PRDs verbatim — the
> §9.13 fetch is satisfied), both build plans are drafted and reconciled
> against it, and SIE runs **ScrapeOwl + TextRazor as newly provisioned
> services** (NER provider amended Google NLP → TextRazor, 2026-06-12 fifth
> pass; retires §9.1's "no new third-party deps" line).
> **M12/M13 prerequisites are DONE (2026-06-15):** `SCRAPEOWL_API_KEY` +
> `TEXTRAZOR_API_KEY` are provisioned on the `info-site-kw-research-cluster`
> Railway **service**, DataForSEO "LLM Responses" is enabled on our account, and
> **all 18 plan sign-off flags are resolved** (SIE §9 / Brief Gen §7 / Writer §8).
> **Embeddings: tried Gemini, ROLLED BACK to OpenAI (2026-06-16).** The 2026-06-15
> swap to **Gemini Embedding 2** (`gemini-embedding-2-preview`) was deployed
> (`bf01879`) + flipped live + health-verified, but in write-time calibration Gemini
> gave **poor relevance discrimination** — off-topic keywords passed the gate even at
> `relevance_threshold` 0.90 (cosines compressed too high; likely the
> `SEMANTIC_SIMILARITY` task type and/or preview-model behavior). **Reverted by
> setting `EMBEDDING_PROVIDER=openai`** (one env var; no code change, no
> recalibration — back to `text-embedding-3-small` + the original `0.65` thresholds).
> The provider-pluggable embedder + per-session guard + `/debug/embedding-health`
> **stay in place (dormant)** for a future revisit (Embedding 2 at GA and/or
> `RETRIEVAL_*` task types → would need a re-embed + recalibration). Caught entirely
> in calibration — **no production data affected.**

_2026-06-21 — M12 (SIE Term & Entity module) CODE-COMPLETE, pending deploy:_

- **Built the full 14-module SIE pipeline** (`backend/app/sie/`, plan
  `docs/sie-module-plan.md`, spec PRD #3) on `claude/optimistic-brown-9wijtx` in 6
  committed slices: foundation (migration `20260621000000_sie_keyword_analyses.sql`
  cross-session 7-day cache + RLS mirroring `site_architecture`; Final Output Model
  `models.py` = Writer **Input C, schema_version 1.4**); pure core (M5-14:
  extract/ngrams/filters/scoring — 5 noise layers, n-grams+subsumption+coverage gate,
  TF-IDF, 6-weight scoring + quadgram multipliers, safe/aggressive usage ranges);
  egress clients (M2-4,10-11: DataForSEO `serp_top_results`, Haiku URL classify +
  pure near-dup, ScrapeOwl, TextRazor NER pass-1 + Sonnet pass-2 with may-not-invent
  guard, OpenAI semantic + dynamic threshold, entity→term merge w/ dual-signal
  1.15x); orchestration (`pipeline.analyze` M1→M14, `cache.py`, `run_sie_job`
  `@_metered("sie_analysis")`); owner-only `term-analysis` API + `TermAnalysisPanel`
  report UI; deps (bs4/lxml/spaCy + `en_core_web_sm` in the Dockerfile).
- **Reconciliations:** SIE uses the session's `location_code` (E1), not the plan's
  hardcoded 2840; built `models.py` to the live Input C **1.4** (consumer wins), so
  per-term confidence/reason aren't persisted (report shows score+entity+usage).
- **Validation:** **23 pure-module tests green in-sandbox** (stdlib only — the
  egress clients lazy-import httpx/spaCy/app so the pure heart stays testable); ruff
  clean; **frontend build green**. **Egress UNVALIDATED** (sandbox can't reach
  DataForSEO/ScrapeOwl/TextRazor/OpenAI) — live-validate on deploy.
- **Remaining to ship:** (1) ✅ **migration APPLIED to prod 2026-06-21**
  (`20260621000000_sie_keyword_analyses.sql`, AR-Internal-Tools; verified table + RLS
  + 4 policies + 2 indexes + 2 FKs; backward-compatible, current `main` doesn't touch
  it); (2) ✅ **MERGED to `main` + DEPLOYED** (`b104405`; Railway `46ea998a` SUCCESS —
  the spaCy/lxml/bs4 build + en_core_web_sm download resolved + started clean);
  (3) **live-validate via the owner Term-analysis action on a real cluster keyword**
  (first real egress run — expect calibration on ScrapeOwl/TextRazor response shapes +
  the Haiku/Sonnet tool schemas), then **STOP FOR REVIEW** (milestone discipline).

_2026-06-17 — Brief Generator (M13) re-aimed ANSWER-ENGINE-FIRST; new AIO
planning doc. Docs-only, on branch `claude/optimistic-brown-9wijtx` (NOT merged
to `main`, no code touched):_

- **New planning doc: `docs/aio-optimization-plan.md`** — captures a body of
  owner-supplied research on optimizing content for **Google AI Overview (AIO) +
  ChatGPT citation**, the gap analysis against the current plans, the collision
  analysis, all owner decisions below, and the source research verbatim
  (Appendix). This is the single source of truth for the AIO/answer-engine work.
  **Registered in CLAUDE.md "Key file locations"** (auto-loads each session).
- **Gap analysis.** The AIO research is **~85% net-new** — `grep` across all of
  `docs/` returns zero prior matches for `AIO`/`main_entity`/`Max Cosine`/
  `decision-fit`. It lands **almost entirely on Brief Gen (M13)**; **nothing on
  SIE (M12)** (SIE only contributes its already-locked spaCy `en_core_web_sm`
  dep); one piece (decision-fit *rendering*) on the Writer (M14). Decision-fit
  mapping is **co-owned** — brief-side trigger/gating + a `format_directive`,
  writer-side prose render.
- **Owner decision #1 — embeddings (DUAL/TRIPLE-SPACE).** Resolves the M13
  embedding-model choice the 2026-06-16 entry re-opened. **Gemini Embedding 2 for
  the AIO-proximity path ONLY**; **`text-embedding-3-large` for the organic
  eligibility gates AND ChatGPT-proximity** (matches GPT's judge). Safe because
  proximity is self-contained and **scalar cosines are blended, never vectors** —
  the "never mix vector spaces" lock holds. Invoke the dormant `GeminiEmbedder`
  directly (independent of the app-wide `EMBEDDING_PROVIDER=openai`, which stays).
  Open: Gemini **task type** (avoid `SEMANTIC_SIMILARITY`, the 06-16 suspect; try
  `RETRIEVAL_*`) — now higher-stakes since proximity drives selection.
- **Owner decision #2 — STRATEGIC PIVOT: answer-engine-first.** The brief
  generator now optimizes **AIO + ChatGPT citation as the PRIMARY target; organic
  ranking is the floor, not the goal.** **Divergence from the PRD/organic-first
  brief-gen design — flagged.** Organic is kept only as the "entry ticket" (AIO/
  ChatGPT pull from the ranked/retrieved set; you must be in it to be cited).
- **Owner decision #3 — FULL MCS selection.** Max Cosine Synthesis **replaces**
  the organic priority/MMR/region/information-gain selection layer: per heading
  slot, generate a large candidate pool (entity+one-point form baked in), score
  by cosine to the AIO + ChatGPT answers (dual-space, scalar-blended), beam-climb
  for set coverage. The eligibility gates (relevance floor + entity-stripped
  restatement ceiling) **demote to a pre-filter**; the 0.20 information-gain
  weight is **removed**; no-EMQ-stuffing becomes default. The ChatGPT answer is
  **promoted from a Step-2D fan-out source to a selection target**. **Accepted
  risk (owner):** proximity is the research's own *low-confidence* citation signal
  ("necessary-not-sufficient") — the X.6 measurement loop is **now required**, not
  deferred, to find out if it pays.
- **Heading-selection rationale "orchestrator" — considered, HELD OFF (owner,
  2026-06-17).** MCS makes selection opaque (pure numeric proximity); there is **no
  component that explains *why* a heading was measured/chosen** (only a
  `discarded_headings` "why-not" record + `title_rationale` for the title +
  aggregate §X.8 metadata). A deterministic "selection rationale ledger" (cheap —
  MCS already computes the signals) was scoped + pros/cons weighed; **owner chose
  to hold off for now.** Revisit when MCS is being built/validated (it's the
  natural instrument for the X.6 loop).
- **Section-1 design decisions are now all RESOLVED** (owner batch 2026-06-17,
  after this entry's first draft): engine set (AIO + ChatGPT), weighting (0.5/0.5),
  stopping rule, Gemini task type (`RETRIEVAL_*`), AIO TTL (shared 7-day), v2.6
  rebase (directive-now), gates-as-pre-filter, ChatGPT (accept + validate via X.6),
  and **H3 generation = HYBRID** (the late-caught item). See the doc's §0/§4/§6.
- **Decision-fit mapping fully specced on the brief side** (doc §3.1–§3.4). Mechanism
  A1–A5: A1 detect (Step-3 intent fold-in, LLM-judged, gate = `confidence ≥ 0.7` AND
  ≥2 distinct conditions) → A2 reserve an anchor H2 (MCS won't drop it; X.4 still
  form-enforces) → A3 source conditions+default (persona-gap/PAA/Reddit) → A4
  pairing/gating co-occurrence check → A5 emit a typed `format_directive`. Writer-side
  render+validate (B1/B2) deferred to M14. **Three spec gaps closed 2026-06-17:** A1
  detector (§3.2) + A5 directive schema (§3.3) specced; **Commercial Page Gating
  DEFERRED** (§3.4 — source not in our excerpt; A4 gates on the three general partner
  factors only, `multiple_languages` dropped from the directive enum; revisit when the
  owner supplies the section).
- **Pre-build verifications — both do-now ones now DONE (2026-06-17):**
  - ✅ **MCS cost estimate** (doc §5.5): embeddings are negligible (~cents; a heading
    is ~12 tok), the driver is LLM candidate *generation*. Bounded shared pool + Haiku
    ≈ **$0.09–$0.27/article** (under the brief budget); literal per-slot×hundreds ≈
    $0.34–$1.03 (risks the $1.00 ceiling). **One open tuning call: cap the pool small
    or raise the brief ceiling to ~$1.25.**
  - ✅ **DataForSEO AIO block** (doc §5.6): CONFIRMED — the advanced endpoint we
    already call at depth 20 returns a structured `ai_overview` item (text + quoted
    sources → X.1's `answer_text`/`cited_sources`). Synchronous AIOs free on the
    existing call; async needs `load_async_ai_overview: true` (+$0.0006, refunded if
    absent/cached). X.1 rides the Step-1 SERP call with one added param. (Docs-sourced;
    confirm field shapes on first deployed run.)
  - ⏳ **Still gated:** the v2.6 **plan-doc reconciliation** at M13 build start
    (directive locked) — must **map authority gaps to H3** (resolved 2026-06-17:
    authority gaps are H3s, deliberately NOT entity-form-enforced — flagged divergence
    from the research's X.4/X.9). Then the build itself, behind M12/SIE.
- **Efficiency/streamlining decisions — adopted 2026-06-17 (doc §5.7), build-time:**
  E1 **per-country locale** (international client — country input at session level,
  English retained; lifts the US/`en` lock; ⚠️ also needs the BUILT M1–M11 pipeline
  made locale-configurable: `sessions` field + migration + client/config constants —
  a real code task, the international-client enabler); E2 **shared SERP fetch** between
  Brief Gen & SIE (they duplicate it today); E3 **conditional Gemini path** (skip when
  `aio_target.present==false`); E4 **trim the fan-out to ChatGPT + Gemini** (drop Claude
  + Perplexity); E5 **content-hash embedding cache**; E6 **intra-brief parallelism**;
  E7 **batch MCS candidate gen across slots**. All design-locked into the plan; code at
  M12/M13 build time (E1 partly sooner if the international client needs research now).
- **E1 per-country locale — ✅ MERGED TO `main` + DEPLOYING (2026-06-17)** (international
  client is live). USA/UK/CA/AU/NZ country dropdown at session creation (owner + VA) →
  DataForSEO `location_code` (language stays `en`). Threaded via
  `DataForSEOClient(location_code=…)` + `get_dataforseo(loc)` (per-locale `@lru_cache`) +
  `store.session_location_code(session)` at all 6 call sites; `create_session` persists it;
  API allow-lists the 5 codes (422 otherwise). Country list lives in **3 places** (API set
  `storage/silo.SUPPORTED_LOCATION_CODES` / DB check constraint / frontend `SUPPORTED_COUNTRIES`)
  — adding a market touches all three. Overrides the US/English locale lock (flagged divergence).
  - **Deploy sequence DONE (2026-06-17), in order:**
    1. **Migration applied to prod** (`20260617000000_session_location.sql`, AR-Internal-Tools
       `wvcthtmmcmhkybcesirb`, via Supabase MCP). Verified: `location_code` default `2840` +
       check constraint present + **all 8 existing rows backfilled to US**. (Migration was
       mandatory-FIRST: only the read path defaults to 2840; `create_session` *writes* the
       column, so code-before-migration would 500 new sessions.)
    2. **Build confirmed green** — note: NO GitHub Actions test/build CI exists (only
       `pages-build-deployment`); the repo builds at deploy time. Confirmed directly with
       `npm ci && npm run build` (tsc + vite, exit 0) — the previously-unverified frontend risk.
       Backend ruff/py_compile clean; **backend pytest NOT run in-sandbox** (PyJWT system-pkg
       conflict + python-louvain wheel fail — environmental). `tests/test_locale.py` runs in
       a real env.
    3. **Merged `claude/optimistic-brown-9wijtx` → `main` `--no-ff` (`beea52f`)**, 23 commits
       (E1 code + all AIO planning docs), zero divergence. Push triggered Railway (backend) +
       Netlify (frontend) auto-deploy. Railway `info-site-kw-research-cluster` deploy
       `df12e5b1` = **✅ SUCCESS** (backend live with the new code; migration already
       applied so it finds `location_code`). E1 is fully shipped.
  - **Adversarial review (`c01bd1c`): no logic bugs.** End-to-end UK trace (2826 → all
    SERP/expansion localized); all 6 sites carry `location_code` (`get_session` `select("*")`,
    `update_session`/insert return the row); 422 on bad codes; no existing test touches
    `create_session`; client immutable/thread-safe. Fixes: migration `if not exists`; corrected
    the "dormant-safe" wording.

_2026-06-16 — Gemini embeddings cutover executed, then ROLLED BACK; logging gap
noted; build path resumes at M12=SIE:_

- **Cutover was carried all the way live, then reverted (same wave).** The
  2026-06-15 swap went: branch merged to `main` + deployed (`bf01879`), migration
  `20260615000000_session_embedding_model` applied to prod, `EMBEDDING_PROVIDER=gemini`
  set + smoke-tested green via `GET /debug/embedding-health`, then model upgraded to
  **Gemini Embedding 2** (`gemini-embedding-2-preview`, public preview) + health-verified.
- **Why rolled back:** write-time calibration on `retatrutide` showed **poor relevance
  discrimination** — off-topic keywords survived the relevance gate even after sweeping
  `relevance_threshold` 0.65 → 0.85 → 0.88 → 0.90 via `/regate` (cosines compressed too
  high to separate on-topic from off-topic; prime suspect = the `SEMANTIC_SIMILARITY`
  task type, possibly preview-model behavior).
- **Rollback = one env var:** `EMBEDDING_PROVIDER=openai` on the Railway service (no code
  change, no recalibration — OpenAI `text-embedding-3-small` + the original
  0.65/0.55/0.85/… thresholds restored). **Caught entirely in calibration; ZERO
  production data affected** — the staged "deploy-dormant → calibrate-before-real-work"
  plan did exactly its job. CLAUDE.md v1.15 records it; config `gemini_embedding_model`
  default reverted preview → GA `gemini-embedding-001`.
- **Gemini infra kept dormant** (not deleted): `GeminiEmbedder`, the per-session
  `embedding_model` 409 guard, the cost rates, `GET /debug/embedding-health`, and the
  `sessions.embedding_model` column/migration all stay. Revisiting Gemini later = flip
  the var + a re-embed + threshold recalibration — best tried with **`RETRIEVAL_*` task
  types** (the likely fix for the discrimination problem) and/or Embedding 2 at **GA**.
- **Brief Generator (M13) Gemini usage is INDEPENDENT of all this.** "Gemini in the brief
  generator" means either **(a)** Gemini as one of the 4 Step-2D fan-out LLMs (DataForSEO
  "LLM Responses" — Gemini-the-LLM, already in the M13 plan, untouched by the rollback),
  and/or **(b)** Gemini *embeddings* inside the brief module (a per-module choice made at
  M13 build time). The app-wide embeddings rollback constrains neither. **Done
  2026-06-16:** the brief-plan §7.3 note (which had marked `text-embedding-3-large` as
  "superseded by the Gemini swap") is un-staled and **re-opened as an M13 embedding-model
  decision** — choose at build time among 3-large (original exception, keeps the
  PRD-calibrated gates; recommended), 3-small (app default, recalibrate the 4 gates), or
  Gemini with `RETRIEVAL_*` task types once validated.
- **Logging — exists, with one worthwhile gap.** Structured JSON logging is in place (§16.3:
  `step_complete` / `degraded` / `external_call` with cost+latency / `llm_call`, every entry
  carrying `session_id` + `correlation_id`, secrets redacted; visible in Railway logs + the
  owner `GET /sessions/{id}/debug`). **Gap (recommended, NOT yet built):** the relevance gate
  logs keep/drop *counts* + threshold but not the score *distribution* — adding min/p10/p50/
  p90/max of the relevance cosines (kept vs dropped) + cluster cohesion to the existing
  `step_complete` events would have surfaced the Gemini compression from a single log line.
  ~15 lines in `relevance.py` / `clustering.py`. Awaiting go-ahead.
- **Next:** the embeddings detour is concluded (OpenAI is the live embedding again); the
  build path returns to **M12 = SIE** per the §9.10 sequence.

_2026-06-15 — planning consolidation + sign-offs + embeddings provider swap (this
session; all on `claude/focused-wright-kj3gyr`, NOT yet merged to `main`):_

- **Consolidated the two divergent Blog-Writer planning branches**
  (`claude/peaceful-mayer-iho6m4` + `claude/wizardly-clarke-3zxvh4`) into one set:
  the 8-PRD bundle (deduped — kept `blog-writer-pipeline-bundle.md`), the live I/O
  contract (`blog-writer-live-contract.md`), and the SIE/Brief-Gen/Writer module
  plans, with `CLAUDE.md` + this file reconciled to the M12=SIE / M13=BriefGen /
  M14=Writer / M15=scheduling sequence (CLAUDE.md v1.12). Both source branches
  stay on `origin` for provenance.
- **Owner sign-off recorded on all 18 flagged plan decisions** (+ one surfaced H3
  conflict). Highlights: SIE lemmatizer = **spaCy `en_core_web_sm`** (shared lock
  w/ the Writer term audit); `fanout.keyword_analyses` RLS = match the other
  fanout tables; Brief Gen **fails the run on abort** (no degraded fallback);
  **low-intent (<0.75) articles BLOCK** until a manual owner intent-override
  (needs a parked state + an override affordance — more build than proceed+warn);
  Writer keeps citable-claim detection in no-citations mode, collapses the title
  to `brief.title`, **builds the pillar path in M14** (scope expanded), and
  **emits H3s from day one** (Brief Gen sources them — supersedes the stale
  "H2-only"). Full text in the SIE §9 / Brief Gen §7 / Writer §8 sign-off blocks.
- **DataForSEO "LLM Responses" confirmed enabled** on our account → M13's Step-2D
  4-LLM fan-out runs at full quality (the `llm_fanout_unavailable` degradation
  stays a runtime safety net only).
- **Embeddings provider swap — locked-decision override (owner): OpenAI
  `text-embedding-3-small` → Google `gemini-embedding-001` @ 1536-dim (Matryoshka),
  whole-app, quality/consistency.** Shipped **DORMANT** (`embedding_provider`
  defaults to `openai`, so prod is untouched until cutover). Code: provider-pluggable
  `backend/app/llm/embeddings.py` (`OpenAIEmbedder` + `GeminiEmbedder` — REST
  `:batchEmbedContents`, `x-goog-api-key` header auth, `outputDimensionality=1536`
  + L2-normalize, 100/req chunks run **concurrently** via `ContextThreadPoolExecutor`,
  cap `gemini_embedding_max_workers=8`); `OpenAILLM.embed` delegates (the LLMError
  contract preserved); per-session `embedding_model` tag + a **freeze-old-sessions
  409 guard** on expand/regate/fanout/plan-articles/architecture (never mixes
  OpenAI/Gemini vector spaces — both are 1536-dim but different spaces); owner-only
  `GET /debug/embedding-health` probe. **Migration
  `20260615000000_session_embedding_model.sql` APPLIED TO PROD** (AR-Internal-Tools
  `wvcthtmmcmhkybcesirb`, `fanout.sessions`, via Supabase MCP). `GEMINI_API_KEY`
  provisioned. CLAUDE.md v1.13 + the locked-decisions table updated; Brief Gen
  §7.3's `text-embedding-3-large` exception is **superseded** by this.
- **Adversarial self-review of the swap → 6 items, all fixed:** (1) `GeminiEmbedder`
  wraps every malformed-response failure as `EmbeddingError` (it was leaking raw
  `KeyError`/`ValueError` past the `LLMError` contract → unhandled 500s at finalize
  + disambiguation, which catch `LLMError` only); (2) parallel chunking (above);
  (3) `split.py` degrades on an embed failure instead of aborting the plan job;
  (4) `OpenAIEmbedder` orders results by the response `index` (Gemini has no index
  field — documented, count-checked); (5) per-chunk cost metering so a partial
  batch failure still attributes the completed chunks. ruff + py_compile clean;
  logic validated against the real `CostMeter` (full pytest runs in CI — no deps
  in the sandbox).
- **Remaining to cut the swap over (ops + live):** deploy this branch (merge to
  `main`), smoke-test `GET /debug/embedding-health` (expect `ok:true`,
  `returned_dim:1536`), set `EMBEDDING_PROVIDER=gemini` + redeploy, then
  **recalibrate the 8 cosine thresholds** on live Gemini runs (relevance 0.65 /
  clustering 0.55 / dedup 0.85 / lateral 0.55 / orphan 0.65 / split 0.55 /
  ambiguity 0.5 / routing-margin 0.04 — all env-overridable + `/regate`-tunable, no
  per-tweak redeploy). Brief Gen's gates (0.55/0.78/0.65/0.75) recalibrate too. If
  Gemini 429s on big runs, lower `GEMINI_EMBEDDING_MAX_WORKERS`.

_2026-06-12 (sixth pass — full Brief Generator pulled into scope, write-time
only): **The complete Brief Generator pipeline (PRD #2 v2.3, Steps 0–11) now
runs for every article at write time** (owner decision; rationale: the process
must be identical for every article). Same lazy rule as SIE: it executes only
as a stage of generating a specific article, never during keyword
research/planning, never bulk-prefetched. **Sequence re-set again: M12 = SIE →
M13 = Brief Generator (new `docs/brief-generator-module-plan.md`) → M14 =
Writer → M15 = scheduling + link injection.** Provider audit (from the PRD's
own cost model): **zero new services** — Reddit search AND the 4-LLM fan-out
(ChatGPT/Claude/Gemini/Perplexity) are DataForSEO endpoints (Reddit search +
"LLM Responses"; verify the latter is enabled on our plan), alongside SERP /
PAA / autocomplete / suggestions we already use; embeddings are OpenAI
`text-embedding-3-large` **inside Brief Gen only** (PRD-calibrated gates
0.55/0.78/0.65/0.75 — flagged scoped exception to the app's 3-small lock).
Step 12 (silo identification) is **skipped** (this app owns silos;
`discarded_headings` persisted for future spin-off intel — flagged). New
`fanout.briefs` cache mirrors `keyword_analyses` (keyword+location, 7-day,
RLS on day one); new `brief_generation` meter phase. **Writer-plan impact:**
adapter calls A1–A4 dissolve (Brief Gen output IS Writer Input A), deltas
Δ1/Δ2 dissolve, H3s + authority-gap sections return, `clusters.adapter_cache`
dropped, the stub fallback demoted to test fixture (a Brief Gen abort fails
the run — no thinner-brief fallback in prod). Cost per brief $0.37–$0.91
(ceiling $1.00); per-article totals now ≈ **$0.92–$1.96 and ~3–5 min**
(brief ∥ SIE, then Writer); a 315-article session ≈ $290–620 spread across
the drip window. Six flags await sign-off in the brief-gen plan §7 (incl. the
v1.7-§5 Step-2 spec gap — sub-source mechanics reconstructed from the v2.x
doc; fetch v1.7 §5 or sample `briefs_cache` rows if ambiguity bites). Docs
only; nothing built._

_2026-06-12 (fifth pass — SIE NER provider amended): **Google Cloud NLP →
TextRazor** for SIE Module-11 entity extraction (owner decision, amending the
third-pass "match PRD exactly" provider lock; ScrapeOwl unchanged). The PRD's
Module-11 *design* is preserved — a grounded NER pass 1 whose output the LLM
pass 2 may dedupe/categorize/filter but never add to — with TextRazor
supplying pass 1 (`app/sie/textrazor_client.py`, httpx REST,
`extractors=entities`, one document per request). Google-specific parameters
become calibration items (SIE plan §9 #6): salience ≥ 0.40 → TextRazor
`relevanceScore` ≥ 0.40 (starting point), the Google entity-type whitelist →
an equivalent DBpedia-type whitelist, the 100KB input cap kept as our
truncation rule (non-binding for TextRazor). Billing is subscription/daily-
quota, so the meter carries an amortized per-request estimate. **Env var
change: `TEXTRAZOR_API_KEY` replaces `GOOGLE_NLP_API_KEY`** in the owner
provisioning prerequisite (ScrapeOwl's key unchanged). Updated: SIE plan
(decision #2 + module table + §3/§4/§7/§9 #6), writer-plan banner, the §9.11
provider row, CLAUDE.md locked-decisions row. Docs only; nothing built._

_2026-06-12 (fourth pass — SIE trigger timing locked): **SIE runs lazily, at
write time only** (owner decision). It executes solely as **stage 1 of
generating a specific article** (M13 `run_article_job`: `keyword_analyses`
cache check → run on miss/stale → adapt → write; M14 scheduled runs do the
same at their scheduled time). It is **never** invoked during keyword
research/planning — no SIE hooks in `/expand`, `/plan-articles`, `/regate`,
`/fanout`, or `/architecture` — and it is **not bulk-prefetched** at
`Schedule all` time, so an article that is never written never incurs SIE
spend (a 315-article session's ≈$100–190 of SIE cost is spread across the
drip window, not paid up front; per-article worker time ≈ 2–4 min incl. the
write). The M12 `Term analysis` endpoint stays single-cluster, owner-only —
a validation surface, not an eager-analysis pathway. Encoded in
`docs/sie-module-plan.md` (decision #4 + §6/§7/§11), the writer plan banner,
and the §9.11 table._

_2026-06-12 (third pass — SIE pulled into scope; sequence re-set): **Three
owner decisions in-session.** **(1) SIE is IN scope** — reopens §9.11's "Skip
SIE in v1" lock; on-page term/entity intelligence (SurferSEO/Clearscope-style)
is required for SEO-competitive output. **(2) Match the SIE PRD exactly on
providers:** **ScrapeOwl** (scraping) + **Google Cloud NLP** (`analyzeEntities`
NER) become **newly provisioned services** (substitutions via DataForSEO
content-parsing / Claude extraction were offered and declined). This retires
§9.1's "no new third-party deps" line. **Owner prerequisite before M12 live
validation: provision `SCRAPEOWL_API_KEY` + `GOOGLE_NLP_API_KEY` (Railway
project level).** **(3) Sequencing = SIE first:** **M12 = SIE → M13 = Writer →
M14 = scheduling + link injection** (first articles are born enriched; Writer
contract validates in M13). Artifacts: new **`docs/sie-module-plan.md`** (full
14-module port per the PRD's MVP list; `fanout.keyword_analyses` 7-day cache
with RLS ON from day one — the §8.7 `sie_cache` lesson; new `sie_analysis`
meter phase; ~$0.30–$0.60 + 1–3 min per keyword, ≈+$100–190 on a 315-article
session — must be included in M14's `Schedule all` cost preview); the Writer
plan **renamed `m12-writer-foundation-plan.md` → `docs/writer-module-plan.md`**
with a re-sequence banner (adapter now consumes real `keyword_analyses`; flat
stub demoted to fallback; Δ4 relaxations largely fall away; C6 claim pattern
activates). Flags awaiting owner sign-off: SIE plan §9 (5 items, incl.
lemmatizer choice — shared with the Writer's future term audit) + writer plan
§8 (6 items). Docs only; nothing built._

_2026-06-12 (later — M13 Writer plan drafted; was "M12" at drafting time,
re-sequenced same day — see the entry above): **Reconciled the §9 sketch
against the real Writer PRD and drafted the Writer build plan** at
**`docs/writer-module-plan.md`** (docs only, nothing built). The sketch
held up; four deltas found and resolved in the plan: **(Δ1)** the adapter gains a
**4th cached LLM call — heading-structure generation** (the predicted H2 gap;
guided by Brief Gen v2.3's `intent_format_template` registry, transcribed
verbatim into `writer/templates.py`; H2-only in v1); **(Δ2)** title + scope are
one call with Brief Gen Step 3.5's real contract (50–80-char title, ≤500-char
scope with a "does not cover" clause), not a derivation; **(Δ3)** §5.8.8
citable-claim coverage should NOT be fully skipped in no-citations mode — its
rewrite-to-remove retry + C7–C9 auto-soften is an anti-fabrication guard
(recommended keep, config-flagged; diverges from §9.1's "skip" — flagged);
**(Δ4)** two degraded-mode relaxations the PRD doesn't define (lede entity rule
→ top supporting keyword; flat term-zone defaults). Also: PRD §17 model tiers
adopted exactly (Sonnet 4.6 prose / Haiku 4.5 short calls, no Opus);
`output.title` collapsed onto `brief.title` (flagged); pillar generation
deferred to M13; M12 migration = `clusters.adapter_cache` + `fanout.
article_outputs` only (slug / site_base_url / schedules are M13-owned). Six
flagged decisions for owner sign-off in the plan's §8._

_2026-06-12 (M12 unblocked — Blog Writer PRD bundle landed): **The AR Tools Blog
Writer PRD bundle is now in the repo** at `docs/blog-writer-pipeline-bundle.md`
(468 KB / 8,867 lines — all 8 PRDs concatenated verbatim: Content Writer
consolidated v1.7 [incl. §17 LLM Call Inventory, §18 Prompt Scaffolds, §19
Closures, §20 golden example] + Brief Generator v2.3 + SIE Term & Entity +
Research & Citations v1.1.1 + Sources Cited v1.1 + Content Quality v1.0 + Suite
Architecture & Roadmap v1.0 + Engineering Implementation Spec v1.1). This
**satisfies the §9.13 Tier-1/2 fetch** that blocked M12 — owner uploaded it
out-of-band (originally in a separate chat) and it was committed here so it
survives container resets. Referenced from CLAUDE.md "Key file locations". Kept
as **one verbatim file** (not split, not folded into the topic-fanout PRD — it's
a different product's spec this app consumes). **Next before any Writer code:**
read the Writer Module PRD (#1) + Engineering Spec (#8) and reconcile the §9
sketch (built from a summary) against them — flagged delta is the empty
`clusters.h2_outline` (the Writer PRD assumes a rich `brief.heading_structure[]`;
the adapter/Writer must now generate body H2s itself — §9.13 closing note). No
code changes in this entry; docs only._

_2026-06-11 (doc sync, no code changes): **CLAUDE.md synced to v1.11** — it had
fallen behind this file (M11 merge/deploy, §7.8 metrics built, writer-owned
H2s/pillar editorial, LLM-free architecture, ≤5-link caps, Opus rate
recalibration are now reflected there; its locked-decisions table updated; this
file added to its Key file locations as the authoritative live log). Stale spots
**inside this file** fixed in the same pass: §1/§2 no longer claim M11 is
unmerged (it merged + deployed by 2026-06-09); §2's duplicated M10 header and
the ancient "then start M11" tail removed; the M11 checklist's "metrics-off
only" caveat updated (§7.8 shipped 2026-05-29) and the closed `_LLM_RATES` item
marked done; §5's `pipeline/architecture/` + `concurrency.py` + `cost_meter.py`
entries updated for the 2026-06-09 LLM-free refactor (verified against current
code). **Then (same day, second pass): §5 fully refreshed module-by-module
against the code on `main`** — now maps the whole post-M11 quality wave that
had gone unrecorded: cooperative cancel (`app/cancellation.py` + `POST
/sessions/{id}/cancel` + `CancelRunButton`), display-time cluster dedupe
(`app/cluster_dedupe.py` + `GET /cluster-keywords`), §7.8 metrics enrichment
(`pipeline/metrics.py`, default ON), pre-embedding language filter
(`pipeline/language.py`), enriched silo anchors (`pipeline/silo_anchor.py`) +
LLM second-pass routing (`pipeline/llm_router.py`), the planning-pass chain
(peer_grouping → split → dedup → orphan_promotion) with auto-accepted coverage
gaps, gate retune (relevance 0.52→**0.65**, 1000/silo cap, forum/social +
past-year junk filters), export-selected, 3 new migrations
(`keyword_metrics` / `keyword_embedding` / `filtered_language` — 14 total, all
in prod), and the frontend wave (real Vol/KD/CPC columns, cluster CSV,
Architecture re-enabled with link_health toolbar, Plan-articles resume action).
§6 counts refreshed: **302 backend tests pass + ruff clean + import smoke OK,
re-verified in-sandbox 2026-06-11** in a fresh venv (`pip install -e ".[dev]"`)._

_2026-06-10 (M12 prerequisites identified — fetch needed before drafting):
**Cannot draft M12 from this repo alone.** §9 references the AR Tools Blog
Writer bundle by step number (Steps 3.5a / 3.5b / 3.6 / 3.8 / 4F / §5.8.8 /
§17 Call Inventory) without ever defining the steps — the source PRDs aren't
in `docs/`. The only Blog Writer artifact in the repo is the §9 summary
itself. Tier-1 fetch list (must have before M12 drafting):
**(1.1) Writer PRD #1 v1.7** — verbatim, with full step list (1→10),
section-call prompts, Brief/SIE input schemas, `article_json` output schema,
§17 Call Inventory, exact behavior of `schema_version_effective:
"1.7-no-context"` and `no_citations: true`, topic-adherence filter mechanic
+ threshold, Agree/Promise/Preview template, CTA template, paragraph-cap +
per-H2-floor numeric values. **(1.2) Engineering Spec PRD** — JSON Schemas
+ module-to-module contracts. Tier-2 (workable but risky without):
**(2.3)** Brief Gen v2.3's `intent_format_template` table (8 rows,
intent_type → format directives); **(2.4)** Content Quality threshold values
if not in 1.1; **(2.5)** 3–5 sample Writer outputs from AR-Internal-Tools
`public.module_outputs` (with matching brief + sie rows by `run_id`) —
ground truth for adapter shape. Tier-3 (huge accelerator): pointer to
AR-Internal-Tools Writer source + production model IDs. **Not needed**
(skipped modules): SIE / Brief Gen full PRDs / Research / Sources Cited /
Content Quality (beyond thresholds) / Suite Architecture PRDs.
**Out-of-band action:** owner is starting a separate chat with access to the
Blog Writer bundle (AR-Internal-Tools repo / Drive folder / AR-Internal-Tools
Supabase `module_outputs`) to fetch these. A self-contained fetch prompt was
drafted in-session — has tier-tagged shopping list + verbatim-not-summarized
rule + per-section output-format spec. When the fetch returns, drop the
artifacts into `docs/blog-writer-prd-v1_7.md` etc. and reference them from
this file + CLAUDE.md before M12 drafting starts. Also flagged: with H2s now
empty at cluster level (2026-06-09 writer-ownership decision), `brief.
heading_structure[]` is much thinner than the external Writer PRD assumes —
the Writer will have to generate body H2s itself, possibly via a new step
the external PRD didn't include. Worth surfacing during M12 design._

_2026-06-09 (§9.9 Writer-integration decisions locked): **All six §9.9
open decisions resolved.** (1) Worker concurrency cap = **3** in-flight (M6
default; revisit after first batch). (2) Re-plan cascade = **warn +
cascade-drop** queued schedules (FK already cascades). (3) Dangling-link
policy = **leave + report** (link_injector keeps the URL; link-health flags
it; not auto-pruned, not batch-blocking). (4) VA scope = **VA full access
on own sessions** (schedule + view + regenerate, RLS-scoped). (5) VA cost
gate (new, derived from #4) = **`Schedule all` > $90 → owner approval** via
the existing M9 `/approvals` queue (new threshold
`writer_schedule_approval_threshold_usd = 90.0`, independent of M9's $5
`va_soft_cap_usd`; per-article `Generate now` not gated). (6) Writer model =
**Sonnet 4.6** for all section calls (PRD §17 lock; ~$0.20–$0.40/article).
§9.11 locked-decisions table updated. M12 (Writer foundation) is now
unblocked — sketch in §9.10._

_2026-06-09 (architecture is now LLM-free; writer owns pillar editorial):
**Removed the per-pillar architect Opus call entirely** (owner decision, merged to
`main` `713da24`). Site-architecture generation is now **fully deterministic** — the
writer module owns the pillar title + summary (placeholder: title = silo name,
summary = ""; target keyword = silo-name-lowercased; H2 outline already empty from
the earlier change). Net −208 lines: gone are `_write_pillar_content` /
`_build_pillar_prompt` / `_stub_pillar_content`, the tool schema + system prompt, the
Anthropic + `ThreadPoolExecutor` imports, the `architect`/`max_workers` params, the
dead `all_degraded()` + the all-degraded error branch (a pillar can no longer
degrade), and the unused `architect_max_workers` config. **No more architecture LLM
cost / latency / rate-limit handling.** `ArchitectureView` shows "Title & summary:
written by the writer module" when the summary is empty. `cost_breakdown`'s
`architecture` phase is now ~$0 (DataForSEO/LLM-free; just embedding reads via the
gate). Flagged divergence from PRD §7.11 (which has Opus write the editorial fields)._

_2026-06-09 (link audit + ArchitectureView fix + review fixes): **(a) Runtime
no-orphan/no-dangling audit** — `ArchitectureResult.link_health()` (orphan_articles
/ orphan_pillars / dangling_links, all 0 by construction) persisted in
`architecture_json`, logged in the job (warns on any non-zero), surfaced in the owner
Debug view + the Architecture toolbar ("✓ no orphans, no dangling links"). Turns the
"by construction" no-orphan claim into a per-run check. **(b) ArchitectureView bug
fix** — the "Links down to" field rendered `articlesForPillar` (ALL children) instead
of the capped `supporting_article_ids`, so pillars *looked* like they had 40+ links
even though the backend cap (≤3) was working; now renders the real down-links with a
count. **(c) Adversarial-review fixes**: `/expand`'s `estimated_cost_usd` write is
best-effort (a DB error there no longer strands the session as `running`); `/expand`
no longer reads topics twice; the dormant owner H2-edit API (`PATCH /clusters`
suggested_h2s) is **closed** (writer owns H2s even at the raw-API level). All merged
to `main`. Live-verified on session `790f750f` (regenerated post-deploy): pillar
down-links capped at 3, article laterals ≤4, `link_health {0,0,0}`._

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

_Last updated: 2026-06-15 — latest: planning consolidated onto `claude/focused-wright-kj3gyr`, all 18 plan sign-offs recorded, and the OpenAI→Gemini embeddings swap shipped dormant (see the 2026-06-15 lead-block entry up top). **§9 below was added 2026-06-09**; its "port **only** the Writer module" framing is superseded by the M12=SIE / M13=Brief Gen / M14=Writer / M15=scheduling re-sequence.
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
— the owner decides the merge. *[Since merged + deployed — live by 2026-06-09.]* Real-metered per-step cost attribution
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
- **M6 — Site architecture (PRD §15.1 / §7.11):** ✅ **complete & signed off (2026-05-26).** `POST /sessions/{id}/architecture` (async, 202) builds one **pillar** per article-bearing silo: Opus 4.7 (reusing the orchestrator client) writes each pillar's editorial fields (title / target keyword / summary / 5–8 H2s) once per pillar in parallel; the **internal linking matrix is assembled deterministically** so the §15.2 rules hold by construction — one pillar/silo, every article up-links to its pillar + pillar down-links to all its articles (⇒ no orphans), pillars link laterally only where topic-embedding cosine > 0.55, and each article gets 2–3 lateral peers (prioritizing M5's `peer_article_links`, filled by same-silo centroid). Persists one `site_architecture` row/session (`session_id` PK, upsert on regenerate per §9.3). `GET /sessions/{id}/architecture` reads it (404 until generated); `GET /summary` now carries an `architecture` block for polling. Per-pillar LLM failure → deterministic stub; all-degraded → `error`. **Validated live on `retatrutide` `4ecefaa1`** (315 clusters, 5 silos): 5 pillars, 0 skipped, 315 supporting articles, **0 orphans, 0 bad parent refs, 945 lateral links (0 dangling)**, all 10 pillar pairs cosine [0.77, 0.85] (>0.55 holds) — all four §15.2 criteria pass; titles are strong (e.g. "How to Get Retatrutide: The Complete Guide to Access, Cost…"). New code: `pipeline/architecture/` (`models.py`, `generate.py`), `run_architecture_job`/`submit_architecture` in `jobs.py`, the two endpoints in `api/sessions.py`, storage helpers (`persist_architecture`, `get_architecture`, `get_cluster_centroids`, `get_keyword_texts`), migration `20260526000000_site_architecture.sql`, `api.ts` (`generateArchitecture`/`getArchitecture` + types). **Post-review fix:** `reset_article_planning` now also clears `site_architecture` (a re-plan/regate/fanout re-creates clusters with fresh ids, so the old architecture would otherwise dangle). **Concurrency fix:** `architect_max_workers` 5→2 + backoff before reprompt — the first live run degraded 3/5 pillars to stubs (transient Anthropic rate-limit under 5 parallel calls, not size-related); the re-run gave 0/5 degraded. Built on `claude/gifted-clarke-pONCI`; merged to `main`. Migration applied to the live DB via Supabase MCP (recorded as version `20260526050706` — the project's migration tracking uses apply-time timestamps, not the repo file prefixes, for every migration). **[Superseded in part 2026-06-09:** the per-pillar Opus call was removed — architecture is now fully deterministic/LLM-free, the writer module owns pillar editorial + H2s; links are capped at ≤5/page with a within-silo-cycle no-orphan guarantee + a runtime `link_health()` audit. See the dated entries at the top.**]**
- **M7 — Owner UI (PRD §15.1 / §9):** ✅ **complete & merged to `main`** (this session, built on `claude/sweet-ramanujan-PXvK0`, merged `--no-ff`). The three views + Split + Project/Session Browser, all editing operations, browser archive/move/delete. An adversarial review pass + fixes ran before merge (architecture invalidation on structural edits; primary-membership guards; idempotent accept-gap). See `CLAUDE.md` "Active milestone" for the full M7a/M7b breakdown + decisions/divergences. Backend 98 tests pass, ruff clean; frontend builds. **Not yet browser-tested** (sandbox egress) — validate on the deployed stack. Remote `main` was at the M6 sign-off (`03c3e54`); the merge added only the M7 commits (`03c3e54..84f96b9`, conflict-free).
- **M8 — VA wizard (PRD §15.1 / §10):** ✅ **complete & merged to `main` (2026-05-26, per owner instruction).** Role-gated app: `App.tsx` reads `me.role` and routes owners to the §9 Owner UI (unchanged) and VAs to a new 9-step linear wizard (`frontend/src/va/Wizard.tsx`) + a restricted results surface. Step gating per §10.1 (disambiguation only when ambiguous; settings limited to topic_count + coverage_mode; deep-mine capped at seed + 2; cost confirmation **stubbed to "Run now"** — approval is M9; progress auto-chains expand → plan-articles). Restricted results reuse the Owner views via a new `role` on `SessionWorkspace`'s `SessionCtx`: VA = Table + Cluster + read-only Architecture (no Split); Cluster = rename + move-keyword only; Table bulk = covered + move only; "Request restructure" is a local stub. **Server-side enforcement** (defense in depth — service-role writes bypass RLS): new `require_owner` dep + `get_role()` (`app/auth/dependencies.py`) gate cluster delete/merge/split/promote-primary, gap accept/dismiss, `/architecture`, session delete, `/regate` + calibration tools, `/fanout`; in-handler checks for the deep-mine cap (`va_deep_mine_max_silos=2`), VA rename-only `PATCH /clusters`, VA no-exclude bulk status. 116 tests (18 new in `tests/test_roles.py`), ruff clean; frontend builds. Built on `claude/exciting-cannon-jTTVb`, merged `--no-ff` to `main`. No schema change. Flagged: architecture owner-only (VA run ends at the plan; Architecture tab owner-pending), metrics toggle decorative (§7.8 unbuilt), no "+ New project" (no endpoint), static cost band.
- **M9 — Approval workflow (PRD §15.1 / §11.3):** ✅ **complete & merged to `main`** (per owner instruction, merged `--no-ff`, conflict-free; still pending live validation). Real cost estimate (pure `app/cost.py`, §8.1-derived); the approval gate sits at the cost-bearing `/expand` (conservative read of §11.3 — silo discovery already runs at `POST /sessions`). VA wizard: CostStep fetches the authoritative estimate and branches under-cap → **Run now** vs over-cap/recursive → **Submit for approval** → **WaitingStep** (polls `/summary` every 30s; cancel; on reject shows the Owner's note + adjust-&-resubmit). Owner: **Approvals** page (`/approvals`) + decision modal (approve/reject + note) + an AppShell nav badge (owner-only, 30s poll). New endpoints: `GET /workspace-settings`, `GET /sessions/{id}/cost-estimate?gated_count=N`, `POST /sessions/{id}/submit-for-approval` + `/cancel-approval` (require_user), `GET /approvals` + `POST /sessions/{id}/approve` + `/reject` (require_owner); `/summary` carries an `approval` block. **No schema change** (M1 already had the columns + `pending_approval`/`rejected`). 139 backend tests (9 in `test_cost.py`, 14 in `test_approvals.py`) + ruff clean; frontend builds. Built on `claude/jolly-heisenberg-Z06PH`, merged `--no-ff` to `main` (conflict-free). See `CLAUDE.md` "Active milestone" for the full breakdown + decisions/divergences (gate placement, reject reuses the session, queue submitted-at = created_at, owner-offline chaining gap, recursive not a VA control).
- **M10 — CSV export (PRD §15.1 / §12):** ✅ **complete & merged to `main`** (per owner instruction, merged `--no-ff`, conflict-free; still pending live validation). Three formats from current Postgres state via pure builders (`backend/app/csv_export.py`): flat (one row/keyword, §9.1 cols, Volume/KD/CPC blank), topic_grouped (one CSV/topic → single `.zip`), architecture (one row/page; 400 if no architecture). Backend uploads to the private `csv-snapshots` bucket + serves a signed URL (`storage/exports.py`); new router `api/exports.py`. Migration `20260528000000_csv_exports.sql` (`fanout.csv_exports` + real RLS) + the bucket applied live via MCP. Frontend Exports tab on both Owner + VA. 164 backend tests + ruff clean, frontend builds. **Storage upload / signed URLs / live round-trip NOT sandbox-validated — deploy-only.** See `CLAUDE.md` "Active milestone" for full decisions/divergences.
- **M11 — Cost confirmation + observability (PRD §15.1 / §16):** ✅ **complete, merged to `main` & deployed** (built on `claude/exciting-davinci-tZGwH`; live by 2026-06-09, meter confirmed working in prod; post-merge fixes 2026-06-09: Opus meter rate (15, 75) → (5, 25), `estimated_cost_usd` persisted on every run path). Real-metered per-step cost → `actual_cost_usd` + new `cost_breakdown` jsonb, flushed live every 10s from the jobs (`app/cost_meter.py` + `app/cost_attribution.py`); `ContextThreadPoolExecutor` (`app/concurrency.py`) propagates the meter + correlation/session ids into nested pipeline threads; the four external-call sites populate `cost_usd`; live cost banner on `/summary` (`shared/CostBanner.tsx`) on Owner + VA; owner-only `GET /sessions/{id}/debug` + `owner/DebugView.tsx` (clustering + orchestrator logs + cost). Migration `20260529000000_session_cost_breakdown.sql` applied live via MCP. 176 backend tests + ruff clean; frontend builds. See `CLAUDE.md` "Active milestone" for full decisions/divergences. **With M11 the M1–M11 build sequence is done — no next milestone; remaining work is live validation (§2).**

## 2. Immediate next action (resume here)

**M11 is merged to `main` and deployed** (live by 2026-06-09; the meter is
confirmed working in prod — see the dated entries above). **The M1–M11 build is
complete.** What remains here is the §15.3 Definition-of-Done live validation
that the sandbox can't run (no egress) — the unchecked items below. Separately,
M12 drafting is blocked on the §9.13 artifact fetch (owner running it
out-of-band).

**M11 live-validation checklist:**
1. Run a standard, metrics-off session through to `complete` (`/expand` →
   `/plan-articles` → `/architecture`). While it runs, confirm the **cost banner**
   on the Owner workspace (and the VA wizard progress screen) shows a climbing
   "Cost so far" that updates roughly every poll (~4s UI / 10s flush).
2. On the completed session, confirm `actual_cost_usd` lands **within ±25% of the
   §8.1 standard estimate (~$2.80)** — §15.3 #7. (§7.8 metrics enrichment shipped
   2026-05-29, so the "+metrics" line CAN now be exercised too — run one
   metrics-on session as well.) ~~Recalibrate `_LLM_RATES`~~ **done 2026-06-09**
   (Opus corrected to the published (5, 25)/1M tok); if cost is still off, the
   remaining estimate error is the `gpt-5.4`/embedding rates (DataForSEO cost is
   the real per-call charge).
3. As **owner**, open **Debug** (link in the session workspace head → `/session/
   :id/debug`): confirm the per-step **cost_breakdown table**, the
   **orchestrator_log** (merge/split/drop rationales + dedup collisions), and the
   **statistical_clustering_log** all render. As a **VA**, confirm `GET
   /sessions/{id}/debug` → **403** (and the Debug link/route are absent).
4. **(Known-open as of 2026-06-09 — needs a fresh pipeline run on the current
   deploy.)** Inspect Railway logs: confirm `external_call` / `llm_call` entries now carry a
   real `cost_usd` (not null) **and** a non-null `session_id` even for the
   nested-thread DataForSEO calls (the `ContextThreadPoolExecutor` fix).
5. Re-run `/plan-articles` (or `/regate`) on the session and confirm
   `actual_cost_usd` **increases** (cumulative real spend) and the
   `article_planning`/`regate` phase in `cost_breakdown` grows — the documented
   cumulative behavior, not a bug.

**M10 live-validation checklist (Storage was unverifiable in the sandbox; M10 is
deployed on `main`):**
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
round-trip and M8's VA/owner routing on the live stack. For M9: (a) as a **VA**, configure an over-cap run (e.g. comprehensive + deep-mine 2 silos, or bump silos high) → the CostStep shows **Submit for approval**, not Run now; click it → the wizard lands on **Waiting for approval** and the session is `pending_approval`; (b) as the **owner**, the topbar **Approvals** badge shows the pending count, the `/approvals` page lists the request, and the decision modal **Approve & run** flips the session to `running` + kicks `/expand` (VA's waiting screen transitions to progress within 30s); (c) **Reject** with a note → the VA's waiting screen shows the note + Adjust & resubmit; (d) a **Cancel request** from the VA returns to the deep-mine step; (e) confirm an *under-cap* VA run still shows **Run now** and runs directly (no approval); (f) hit `GET /approvals`, `POST /sessions/{id}/approve|reject` with a **VA** JWT → 403. **Also still validate M8** (not browser-tested): VA vs owner routing via `/me`, the full VA wizard flow, the restricted results surface, and the owner-only 403s. Carried flags to decide when they next block: `POST /projects` ("+ New project"), per-topic orchestrator re-run, session duplicate, server-side expand→plan chaining + a VA session-resume surface (so an owner-approved run completes even if the VA's browser is closed). (The long-carried "metrics enrichment §7.8 unbuilt" flag is **closed** — metrics shipped 2026-05-29; re-check whether the VA wizard's metrics toggle is still decorative now that the feature exists.)

**Owner-only endpoints (M8, enforce server-side via `require_owner`):** cluster delete/merge/split/promote-primary, `coverage-gaps` accept/dismiss, `POST /architecture`, `DELETE /sessions/{id}`, `/regate`, `/cluster-preview`, `/routing-diagnostic`, `/lever3-simulate`, `/fanout`. A VA gets 403 at the dependency layer (before any DB work). The calibration tools (`/regate` etc.) the M5/M6 console workflow used are now owner-only — fine, since calibration is an owner task, but note it if a VA token is ever used for tuning.

**Settled in M7:** the **orchestrator-vs-direct planner default → orchestrator stays default** (it already was the code default; `direct` remains the opt-in `{"direct": true}` flag, so no code change). M7's "Re-run orchestrator" button uses the orchestrator. Note `4ecefaa1` itself was planned in *direct* mode (315 articles), so re-running it from the UI would consolidate to fewer orchestrator articles — expected.

**M7 carried/deferred (flagged, not blocking):** per-topic orchestrator re-run (only whole-session wired); split option (b) (re-run-on-article); session **duplicate** (§9.4); **metrics enrichment §7.8** still unbuilt so Table View Volume/KD/CPC are "—"; Table cluster-filter is single-select; keyword move uses a select (no drag-drop).

**Calibration workflow that emerged in M5** (reuse it): tuning is done against the **deployed API via browser-console `fetch`** (sandbox has no egress), and results are inspected via the **Supabase MCP tools**, not the UI (no session resume until M7). `/regate` re-runs gate+cluster on the *stored* pool (no DataForSEO) at an overridden threshold / edge / resolution / aliases / peer_entities — the cheap iteration loop. `/cluster-preview` and `/lever3-simulate` are read-only analysis.

**M11 is merged + deployed; once the checklist above completes, the M1–M11 build is fully signed off.** Post-M11 design captured in **§8** (broader "produce a live site" plan) and **§9** (the now-current Writer-module integration direction — 2026-06-09; supersedes §8.5 #1; M12/M13 sketch in §9.10). Both planning-only — nothing built; M12 drafting is blocked on the §9.13 artifact fetch.

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
- `config.py` — `Settings` (pydantic-settings); env aliases; all pipeline knobs. Notable **current** defaults (several drifted from older notes in this file): `relevance_threshold` **0.65** (raised from 0.52 post-M11 to cut keyword count), `active_per_silo_cap` **1000** (post-gate top-N by relevance), `enrich_with_metrics_default` **True** (§7.8 is live), `language_filter_enabled` True (lingua confidence 0.6), `split_oversized_articles` / `peer_entity_grouping` / `promote_orphan_keywords` (floor 0.65) / `enriched_silo_anchor` (30 examples/silo) / `llm_routing_enabled` (margin 0.04) all True, architecture link caps (pillar-down 3 / pillar-lateral 2 / article-lateral 4), `cluster_display_dedupe_cosine_threshold` 0.95.
- `api/` — `health.py`, `projects.py`, `sessions.py`, **`exports.py` (M10)**. Session endpoints: silo discovery, `/finalize`, `/deep-mine`, `/expand` (async), `/plan-articles` (async; body `{"direct": true}` skips the orchestrator), `/regate` (async; body overrides threshold/edge/resolution/aliases/peer_entities), `/fanout` (async; RF §7.7 — cost-gated, `{"confirm_cost": true}` to spend, optional resolution/threshold overrides), `/summary` (poll), `/clusters` (read), `/cluster-preview`, `/routing-diagnostic`, `/lever3-simulate` (read-only analysis), **`/debug` (M11, owner-only — `statistical_clustering_log` + `orchestrator_log` + cost, §15.3 #8)**. **Post-M11 additions:** `POST /sessions/{id}/cancel` (cooperative run cancellation — see `cancellation.py`), `GET /sessions/{id}/cluster-keywords` (the Cluster View read: full surviving set in one shot, each row tagged `dedupe_canonical_id` by the display-time dedupe — Table View/CSV intentionally keep every variant via `/keywords`). **`exports.py` (§12):** `POST /sessions/{id}/export?format=flat|topic_grouped|architecture` (sync — generate + snapshot + record + signed URL), **`POST /sessions/{id}/export-selected` (§9.1 bulk action, post-M11 — transient flat CSV of the selected keyword ids returned directly as a download; no Storage snapshot, no `csv_exports` row; stale/cross-session ids silently drop)**, `GET /sessions/{id}/exports` (the Exports tab list), `GET /exports/{id}/download` (re-sign a fresh URL). All `require_user`, both roles, RLS-scoped.
- `csv_export.py` (**M10**, PRD §12) — **pure** CSV builders (`build_flat_csv`, `build_topic_grouped_csvs` + `zip_named_csvs`, `build_architecture_csv`) over already-fetched rows + CSV formula-injection hardening (`_safe`). No egress; all of M10's correctness coverage is here (`tests/test_csv_export.py`). The Storage upload + signed-URL layer is `storage/exports.py` (deploy-only).
- `auth/dependencies.py` — `require_user` (verifies Supabase JWT via service client; logs real reason on failure). **M8:** `get_role(user)` (reads `user_profiles.role`) + `require_owner` dependency (403 for non-owners) for the §11.2 capability gates.
- `cost.py` (**M9**, PRD §8.1/§8.4) — pure `estimate_cost(...)` (per-component §8.1-derived rates → total + breakdown, recursive ×5) + `requires_approval(...)` (estimate > soft cap OR recursive). No egress; unit-tested in `tests/test_cost.py`. The approval endpoints (`/cost-estimate`, `/submit-for-approval`, `/cancel-approval`, `/approvals`, `/approve`, `/reject`) live in `api/sessions.py`; storage helpers `get_workspace_settings` / `count_gated_topics` / `list_pending_approvals` + the `/summary` `approval` block in `storage/silo.py`.
- `cost_meter.py` (**M11**, PRD §16.4) — the live **actual**-cost machinery (vs. `cost.py`'s estimate). `CostMeter` (thread-safe, per-run, broken down by pipeline phase) + the `_meter`/`_step` contextvars + `record_cost(cost)` (called from the four external-API clients) + the LLM/embedding `$`-per-token rate table (`llm_token_cost` / `embedding_token_cost` — Opus calibrated to the published (5, 25)/1M tok on 2026-06-09; `gpt-5.4`/embedding rates still **estimates**, calibrate per §8.1). DataForSEO cost is the **real** per-call charge from its task envelope. No egress; unit-tested in `tests/test_cost_meter.py`.
- `cost_attribution.py` (**M11**) — bridges the meter to storage: `metered_run(session_id, step)` (background-job context manager: binds the meter on the job thread, periodic + final lock-serialized flush of `actual_cost_usd` + `cost_breakdown`, cumulative onto the existing total) and `metered_sync(session_id, step)` (single final flush, for the synchronous silo-discovery call). `jobs.py` applies a `@_metered("…")` decorator to each job; `api/sessions.py` wraps silo discovery in `metered_sync`.
- `concurrency.py` (**M11**) — `ContextThreadPoolExecutor`: a `ThreadPoolExecutor` whose `submit` runs each task inside a `copy_context()` snapshot, so the meter + `session_id`/`correlation_id` propagate into the pipeline's nested API-call worker threads. Imported under the `ThreadPoolExecutor` alias by `expansion.py` / `competitor.py` / `serp.py` / `orchestrate_articles.py` (no longer `architecture/generate.py` — its executor + Anthropic imports were removed in the 2026-06-09 LLM-free refactor; since then it's also used by `jobs.py`, `pipeline/metrics.py`, `pipeline/llm_router.py`, `pipeline/silo_anchor.py`).
- `cancellation.py` (**post-M11**) — cooperative cancellation: `POST /sessions/{id}/cancel` flips the session to `cancelled` and sets a per-session `threading.Event`; the worker + nested external-call sites call `raise_if_cancelled()` before each request and raise `CancelledByUser` (a **BaseException**, so pipeline `except Exception` handlers don't swallow it), caught at the top of each `run_*_job`. In-flight HTTP isn't aborted (worst case ≈ one 60s DataForSEO timeout); every subsequent call is saved. Frontend: `shared/CancelRunButton.tsx`.
- `cluster_dedupe.py` (**post-M11**) — **display-time** within-cluster keyword dedupe for the Cluster View (pure): pass 1 surface-form normalization (plural lemma, "what is/are X" question folding, leading-article strip, alias map, sorted-token signature), pass 2 cosine collapse on the per-keyword embeddings the gate persists (threshold 0.95); winner = highest volume → relevance → alphabetic. Returns `{keyword_id: canonical_id}`; served via `/cluster-keywords`. Nothing is deleted — Table View and CSV exports still show every variant.
- `storage/supabase_client.py` — service client (RLS-bypass, admin writes) + user client (anon key + user JWT, RLS-enforced reads). `storage/silo.py` — session/topic/keyword/cluster DB ops incl. `set_topics_gating`, `get_topic_embeddings`, `insert_classified_keywords`, `try_mark_running`, `get_session`, `list_all_keyword_pool` (re-gate pool reconstruction), `persist_article_plan` (staged cluster write), `reset_article_planning`, `get_pipeline_summary`, `list_clusters`, **`list_surviving_keywords` (M10, paged active/excluded/covered pool for export)**, **`get_session_cost` / `flush_session_cost` / `get_session_debug` (M11)**. The `/summary` payload now also carries a live `cost` block (`estimated_cost_usd`/`actual_cost_usd`/`breakdown`) in both the cheap-running and full paths. `storage/exports.py` (**M10**) — Supabase **Storage** ops (`upload_snapshot` to the `csv-snapshots` bucket via the service client, `create_signed_url`) + `csv_exports` table ops (`insert_export` [service], `list_exports` / `get_export_visible` [user client, RLS]). **Deploy-only** (sandbox can't reach Storage).
- `llm/openai_client.py` — GPT-5.4 grounding + silo proposal (Responses API + web_search; grounding also emits per-seed `aliases`/`peer_entities` and a per-silo **`relationship_type`** [8 enums — property_or_mechanism, use_case, peer_entity, … — shown in the silo-review UI, used by routing]) + `embed()`.
- `dataforseo/client.py` — DataForSEO calls (demand sample, SERP structure, expansion endpoints, autocomplete; M4: `serp_top_urls`, `ranked_keywords`, `domain_of`; **§7.8: `keyword_overview`** for metrics).
- `pipeline/` — `silo_discovery.py` (M2), `expansion.py` (M3), `competitor.py`/`clustering.py` (M4), `orchestrate.py` (M4 `run_refinement_pipeline` + M5 `gate_and_cluster`/`cluster_preview`/`routing_diagnostic`/`simulate_best_silo_clustering`), `models.py`.
- **The gate (`relevance.py`) now runs, in order:** junk filter (token blocklist **incl. forum/social platform names + a past-only-year filter**, post-M11), off-niche peer-entity filter, **pre-embedding language filter** (`language.py`, post-M11: curated non-English-starter regex + lingua detector at ≥0.6 confidence → new `filtered_language` status; two layers because each catches what the other misses), embedding-cosine gate at threshold 0.65, Lever-3 best-silo routing against **enriched silo anchors** (`silo_anchor.py`, post-M11: rationale embedding centroided with ~30 LLM-generated example keywords per silo, built once at finalize; falls back to rationale-only on failure) with an **LLM second pass for ambiguous keywords** (`llm_router.py`, post-M11: top-1 vs top-2 anchor-cosine margin < 0.04 → batched LLM ruling restricted to the candidate-silo list; batch failure is benign, cosine stands), then the **1000/silo active cap** (top-N by relevance). Active keywords keep their gate embeddings (persisted to `keywords.embedding` for §7.9 reuse + display dedupe).
- `pipeline/metrics.py` (**§7.8, post-M11**) — after gate + cap, batched DataForSEO Labs `keyword_overview` (≤500 kw/call, parallel) → volume / CPC / KD / competition persisted via `update_keyword_metrics`; runs when the session's `enrich_with_metrics` is on (**default now true**); ~$0.40 for a typical 5-silo run.
- `pipeline/article_planning/` (M5 core + **post-M11 passes, applied in this order in `run_plan_job`**): `orchestrate_articles.py` (chunked orchestrator + `direct` mode; transient-transport backoff + lowered worker count) → `peer_grouping.py` (**cross-topic peer-entity partition**: keywords naming the same peer entity collapse into exactly ONE article across the whole plan — embeddings can't tell `tirzepatide` from `zepbound` variants apart, the deterministic peer list can; home topic = biggest contributor; sub-threshold buckets fold into one comparison-roundup article) → `split.py` (**salience split**: re-cluster over-large articles [>40 kw] at finer Louvain resolution; no thin stubs — sub-communities below the floor fold back) → `dedup.py` (cross-topic dedup) → `orphan_promotion.py` (**every gate-active keyword in no article and not formally dropped becomes its own singleton article**; global coverage check, quality floor ≥0.65 anchor cosine; pre-pass this orphaned 44% of the retatrutide pool) → persist. Coverage gaps are **auto-accepted at persist time** as keyword-named `is_gap_placeholder` articles (owner decision; the accept/dismiss endpoints remain for legacy pending gaps). Also: `serp.py`, `models.py`. `jobs.py` — async background worker (`run_expand_job` [expansion → mining → gate → cluster → **metrics**], `run_plan_job`, `run_regate_job`, `run_fanout_job`, `run_architecture_job`; all `@_metered`, all checking `raise_if_cancelled`). `llm/anthropic_client.py` — Opus 4.7 tool-use client.
- `pipeline/recursive_fanout.py` (RF §7.7) — `derive_sub_anchors` (top-N cluster reps per silo), `run_recursive_expansion` (reuses `run_expansion`, remaps synthetic sub-anchor topics back to parent silos, tags `recursive`), `merge_into_pool`. Drives `run_fanout_job`.
- `pipeline/architecture/` (M6 §7.11; **rewritten 2026-06-09 — fully deterministic, LLM-free**) — `models.py` (`PillarInput`/`ArticleInput` in, `Pillar`/`SupportingArticle`/`ArchitectureResult` out; `architecture_json()` = the stored shape, now incl. `link_health()` [orphan_articles / orphan_pillars / dangling_links — 0 by construction]; `all_degraded()` removed, pillars can no longer degrade), `generate.py` (`run_architecture_generation`: `_pillar_content` placeholder editorial [title = silo name, summary empty — the writer module fills at write time] + `_pillar_down_links` [≤3 most-central children] + `_lateral_pillar_links` [cosine > 0.55, ≤2] + `_lateral_article_links` [1 up-link + ≤4 laterals incl. the within-silo cycle successor = the no-orphan guarantee]). No Anthropic client, no executor. Drives `run_architecture_job` in `jobs.py`.

Frontend M9 additions: `owner/ApprovalsPage.tsx` (route `/approvals`, owner-only) — the approval queue + a decision modal (approve/reject + note), 30s poll. `shared/AppShell.tsx` gained an owner-only **Approvals** nav link with a pending-count badge (`enabled: isOwner`, 30s poll). `va/Wizard.tsx`: CostStep now fetches `getCostEstimate` and branches Run-now vs Submit-for-approval; new **WaitingStep** (polls `/summary`, cancel via `cancelApproval`, reject shows the note + adjust-&-resubmit); DeepMineStep shows a live server estimate. `shared/api.ts` gained `getCostEstimate` / `getWorkspaceSettings` / `submitForApproval` / `cancelApproval` / `listApprovals` / `approveSession` / `rejectSession` + the `approval` field on `PipelineSummary`. Query key `["approvals"]` (badge + page share it); `["cost-estimate", sessionId, gatedCount]`.

Frontend (M7/M8, react-router): `App.tsx` is **role-gated** — `RoleRoutes` reads `me.role` and renders `OwnerRoutes` (`/projects`, `/session/new`, `/session/:id/{table,cluster,architecture,split}`) or `VaRoutes` (`/wizard`, `/session/:id/{table,cluster,architecture}` — no split; everything else redirects to `/wizard`). On a `/me` failure it falls back to the more-restricted VA routes. `va/Wizard.tsx` (M8) is the 9-step VA wizard (reuses `shared/api.ts`; auto-chains expand→plan in the progress step). `SessionWorkspace`'s `SessionCtx` now carries `role`, which the shared views (`TableView`/`ClusterView`/`ArchitectureView`) read to hide owner-only controls for VAs. `owner/SiloDiscovery.tsx` is the creation+pipeline flow (seed → disambiguation → silo review → finalize → **deep-mine** → run → results), reached via `owner/NewSession.tsx`. `owner/ProjectsPage.tsx` = Project+Session Browser (§9.4) with archive/move/delete. `owner/SessionWorkspace.tsx` = per-session shell (segmented control + status gate) that passes a `{sessionId, topics, topicName}` context to `owner/views/{TableView,ClusterView,ArchitectureView,SplitView}.tsx`. `shared/AppShell.tsx` (topbar), `shared/sessionStatus.ts` (status labels + `hasResults`), `shared/api.ts` (all calls incl. M7b mutations), `shared/auth.tsx`, TanStack Query (query keys: `["clusters",id]`, `["keywords-all",id]` paged surviving pool, `["summary",id]`, `["architecture",id]`, `["sessions",projectId,showArchived]`). Views are read-only when the session lacks results; editing mutations invalidate `clusters`+`keywords-all`.

Schema migrations in `supabase/migrations/`: `..._fanout_initial.sql` (M1), `..._topics.sql` (M2), `..._keywords.sql` (M3), `..._keywords_relevance.sql` (M4), `...20260525000000_clusters.sql` (M5: `clusters` + `coverage_gaps` + orchestrator keyword cols + `awaiting_article_planning` status), `..._session_last_error.sql` (M5), `..._peer_entities.sql` (M5: `sessions.aliases` + `peer_entities`), `...20260526000000_site_architecture.sql` (M6: `site_architecture` table + RLS), `...20260527000000_session_archive.sql` (M7b: `sessions.archived`), `...20260528000000_csv_exports.sql` (**M10**: `csv_exports` table + the `csv_export_format` enum + real RLS via a `sessions`-join), `...20260529000000_session_cost_breakdown.sql` (**M11**: `sessions.cost_breakdown jsonb`; no RLS change), **`...20260530000000_keyword_metrics.sql` (§7.8: volume / cpc_usd / keyword_difficulty / competition_index on `keywords`), `...20260604000000_keyword_embedding.sql` (persist gate embeddings on `keywords` — §7.9 reuse + display dedupe), `...20260604000001_keyword_status_filtered_language.sql` (adds the `filtered_language` enum value — the one that reached prod late, applied 2026-06-09)**. All **14** applied to the live DB via Supabase MCP (2026-06-09 sweep confirmed no gaps; live tracking uses apply-time timestamps, not the repo prefixes). **M9 added no migration** — the approval columns (`estimated_cost_usd`, `actual_cost_usd`, `approval_required`, `approval_decided_by_user_id`, `approval_decision_at`, `approval_note`) and the `pending_approval`/`rejected` statuses were created in the M1 `..._fanout_initial.sql` migration. The **`csv-snapshots` Storage bucket** (private) was also created via MCP for M10 (it's not a SQL migration; `insert into storage.buckets`).

Frontend M10 additions: `owner/views/ExportsView.tsx` (route `exports`, added to **both** the Owner + VA segmented controls in `SessionWorkspace`) — three format Download buttons (architecture disabled until the summary reports an architecture) + a "Past exports" list with per-row re-download; opens the backend-minted signed URL in a new tab. `shared/api.ts` gained `createExport` / `listExports` / `downloadExport` + the `CsvExport*` types. Query key `["exports", sessionId]` (new, no clash); reuses `["summary", sessionId]` to gate the architecture button. CSS: `.export-actions`.

Frontend M11 additions: `shared/CostBanner.tsx` (live actual-vs-estimate cost banner + progress bar; red when actual > estimate) rendered on the Owner `SessionWorkspace` head and the VA wizard `ProgressStep`; both read the new `cost` block on the `/summary` poll. `owner/DebugView.tsx` (route `/session/:id/debug`, **OwnerRoutes only**) — per-step cost table + raw `orchestrator_log` / `statistical_clustering_log`; reached via an owner-only "Debug" link in the workspace head. `shared/api.ts` gained `SummaryCost` (on `PipelineSummary`) + `SessionDebug` + `getSessionDebug`. Query key `["debug", sessionId]`. CSS: `.cost-banner*`, `.debug-link`, `.debug-table`, `.debug-json`.

Frontend post-M11 additions: `shared/CancelRunButton.tsx` (confirm-then-cancel on the Owner workspace head + VA progress screen), `shared/queryClient.ts` (shared TanStack client: retry 1, no refetch-on-focus), `shared/relationshipTypes.ts` (display labels for the per-silo `relationship_type`, used in silo review [Owner + VA] and the Cluster View). **Table View:** real sortable **Vol / KD / CPC** columns (§7.8 — the "—" placeholders are gone) + an **Export selected** bulk action (`exportSelected` → transient CSV blob, downloaded client-side). **Cluster View:** reads `/cluster-keywords` (query key `["cluster-keywords", id]`), renders one canonical variant per intent (display-time dedupe), surfaces the target keyword per article, gained a per-session **Download CSV**; the H2-outline row is gone (writer owns H2s); gap triage UI only renders for legacy pending gaps (new gaps auto-accept as placeholder articles). **Architecture View** was briefly hidden from both surfaces, then **re-enabled** with real capped down-links + the `link_health` toolbar ("✓ no orphans, no dangling links"). **Exports:** CSV downloads are named after the seed keyword; the architecture format carries the internal-linking columns. **SessionWorkspace** gained a **Plan-articles action** (resume path for sessions parked at `awaiting_article_planning`) and the expansion progress estimate now reads 6–10 minutes.

## 6. Useful commands / queries

Backend (from `backend/`; a fresh container has no venv — create it first):
```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
python -m pytest -q          # 302 tests, all passing (verified 2026-06-11)
ruff check app/ tests/       # clean
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

> **[Amended 2026-06-12, owner decisions — see that day's dated entries:
> (a) SIE is no longer skipped — it builds FIRST as M12 (`docs/sie-module-plan.md`),
> with ScrapeOwl + TextRazor as newly provisioned services (NER provider
> amended from Google NLP same day), so the
> "no new third-party deps" line below no longer holds; (b) the Writer's
> `sie` input is the real `keyword_analyses` output, with the flat-keyword
> stub (§9.2) demoted to fallback; (c) §5.8.8 is not fully skipped — its
> rewrite/soften arm is kept as an anti-fabrication guard (writer plan Δ3).
> Brief Generator / Research / Sources Cited remain skipped; `no_citations:
> true` and `1.7-no-context` still apply.]**

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

### 9.9 Open decisions — **RESOLVED 2026-06-09**

All six items resolved in conversation; see §9.11 for the locked decisions
table.

1. **Concurrency cap default** — **3** (the proposed default; revisit after
   first live batch against real Anthropic Sonnet rate limits).
2. **Re-plan cascade** — **Warn + cascade-drop.** UI warns "this will cancel
   N pending schedules"; on confirm, the existing FK cascade drops them.
   Matches the existing pattern where re-plan/regate already discards manual
   edits. Re-target-by-name rejected as too brittle.
3. **Dangling-link policy** — **Leave + report.** Link stays in prose; the
   link-health report (§9.5) flags it; owner can retry the failed article or
   accept the broken link. Auto-prune hides info; blocking the batch on a
   single transient 529 is too fragile.
4. **VA scope** — **VA full access on own sessions** (RLS-scoped to sessions
   they own). VA can schedule, view, regenerate. *But*: see #5 — material
   spend (>$90 per `Schedule all` batch) routes through the approval queue.
5. **VA cost gate (new, derived from #4)** — **`Schedule all` > $90 → owner
   approval required.** New threshold `writer_schedule_approval_threshold_usd
   = 90.0` (independent of the M9 `va_soft_cap_usd = 5.0` which gates
   `/expand`). When a VA's `Schedule all` estimate exceeds the threshold the
   modal shows **Submit for approval** instead of **Schedule now** and reuses
   the M9 `/approvals` queue + decision modal. Per-article `Generate now` for
   a single article is well under any reasonable cap; gate only the batch.
   Owner/admin runs are never gated.
6. **Writer model tier** — **Sonnet 4.6 for all section calls** (PRD §17
   lock). ~$0.20–$0.40/article per §9.1. Predictable cost, easiest to ship.
   §8.3's Opus-on-pillars / Haiku+Opus variants flagged for revisit if Sonnet
   quality disappoints on the first live batch.

### 9.10 Likely milestone sequence — **RE-SET 2026-06-12 (owner; revised twice same day)**

- **M12 — SIE Term & Entity module** (pulled into scope 2026-06-12, reopening
  the §9.11 "skip SIE" lock): full 14-module port per the SIE PRD's MVP list,
  providers **ScrapeOwl + TextRazor, newly provisioned** (NER provider
  amended from Google NLP, 2026-06-12 fifth pass),
  `fanout.keyword_analyses` 7-day cache, owner-only `Term analysis`
  report surface. Runs lazily at write time only.
  **→ Build plan: `docs/sie-module-plan.md`** (flagged decisions in its §9).
- **M13 — Brief Generator** (pulled into scope later 2026-06-12, sixth pass):
  full PRD #2 v2.3 pipeline (Steps 0–11; Step 12 silo-identification skipped —
  this app owns silos), write-time only, **zero new services** (all candidate
  sources are DataForSEO incl. Reddit search + the 4-LLM "LLM Responses"
  fan-out; embeddings `text-embedding-3-large` inside the module).
  `fanout.briefs` 7-day cache; `brief_generation` meter phase.
  **→ Build plan: `docs/brief-generator-module-plan.md`** (6 flags in its §7).
- **M14 — Writer foundation** (was M12, then M13): port Writer module + thin
  field-mapper (Brief Gen output IS Writer Input A) + degraded-mode contract
  (`1.7-no-context`, `no_citations`); manual **`Generate now`** (owner-only).
  At write time: Brief Gen ∥ SIE (stage 1, parallel) → Writer.
  **→ Build plan: `docs/writer-module-plan.md`** (see its banner — adapter
  A1–A4 + deltas Δ1/Δ2 dissolved by M13).
- **M15 — Scheduling + internal linking** (was M13/M14): asyncio worker loop,
  **`Schedule all`** modal (all-at-once + drip), `link_injector`, article
  view, schedule overview, link-health report. Cost preview must include
  Brief Gen + SIE + Writer (≈$0.92–$1.96/article) for uncached keywords.
- **M16 (optional) — Brand voice + citations:** add `fanout.clients`
  layer + bolt in Research module + Sources Cited renderer. Deferred until
  v1 quality is judged insufficient.

### 9.11 Locked decisions (2026-06-09)

| Topic | Decision |
|---|---|
| Integration depth | ~~**Writer + adapter only.** Skip Brief Generator, SIE, Research, Sources Cited.~~ **[Amended twice 2026-06-12: SIE is IN scope (M12, `docs/sie-module-plan.md`, ScrapeOwl + TextRazor) AND the full Brief Generator is IN scope (M13, `docs/brief-generator-module-plan.md`, all-DataForSEO sources, write-time only).** Research + Sources Cited remain skipped (`no_citations: true`).] |
| SIE providers (2026-06-12) | **ScrapeOwl** (scraping, PRD-exact) + **TextRazor** (NER — amended same day from the initially chosen Google Cloud NLP; Module-11 grounded-NER design preserved, Google-specific thresholds become calibration items) provisioned as new services; DataForSEO/Claude substitutions declined. Retires §9.1's "no new third-party deps" line. |
| SIE + Brief Gen trigger timing (2026-06-12) | **Write-time only, lazy — both modules, run in parallel** as stage 1 of generating a specific article (cache check → run on miss/stale); never during research/planning (`/expand`, `/plan-articles`, `/regate`, `/fanout`, `/architecture`); never bulk-prefetched at `Schedule all`. Unwritten articles incur no SIE spend. M12's `Term analysis` endpoint = single-cluster validation surface only. |
| Brand voice | **Skip in v1** (`1.7-no-context`). `clients` layer deferred to v2 (M14). |
| Citations | **Skip in v1** (`no_citations: true`). Research module bolted on later without schema changes. |
| Cadence semantics | **Per-article one-shot publish date.** Recurring refresh deferred. |
| Bulk mode | **All-at-once** OR **drip N/day**, whole-session scope, ≤365d horizon. |
| Drip order | **Pillars first**, then architecture order. |
| Drip days | **Every calendar day** (no weekend skip). |
| Internal-link anchors | **Deterministic injection** (code-finds keyword + wraps; "Related articles" fallback). |
| Internal-link URLs | **Absolute** (`sessions.site_base_url` required to schedule). |
| Cron mechanism | **In-process asyncio loop** (matches M5 `app/jobs.py`). |
| Worker concurrency cap | **3 in-flight** (revisit after first live batch). |
| Re-plan cascade | **Warn + cascade-drop** queued schedules (FK already cascades; UI shows the count). |
| Dangling-link policy | **Leave + report.** link_injector keeps the URL; link-health report flags it. |
| VA scope | **Full access on own sessions** (RLS-scoped). VA can schedule + view + regenerate. |
| VA cost gate (Writer) | **`Schedule all` > $90 → owner approval** via existing M9 `/approvals` queue. New `writer_schedule_approval_threshold_usd = 90.0` (independent of M9's $5 `va_soft_cap_usd`). Per-article `Generate now` not gated. |
| Writer model tier | ~~**Sonnet 4.6 for all section calls**~~ → **MIXED — corrected 2026-06-12 per §17** (see §9.13 status box): **Sonnet 4.6** prose (section/intro/FAQ/conclusion/takeaways) + **Haiku 4.5** title/CTA/ICP-judge. ~$0.20–$0.40/article. |

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

### 9.13 M12 prerequisites — artifact fetch (2026-06-10) — ✅ SATISFIED 2026-06-12

> **✅ RESOLVED 2026-06-12 — the bundle has landed; the content-generation work is UNBLOCKED.**
> The owner dropped the full **8-PRD AR Tools Blog Writer bundle** into
> **`docs/blog-writer-pipeline-bundle.md`** (8,867 lines, one concatenated file with
> `<!-- SOURCE FILE: … -->` markers per PRD): **(1)** Content Writer v1.7 — incl.
> **§17 LLM Call Inventory** (exact model IDs, max-tokens, temps, retries per call),
> **§18 Prompt Scaffolds** (verbatim), **§19 Closures**, **§20 Golden Example**, the
> Step 1→12 flow, the topic-adherence filter (cosine **0.62** to title),
> Agree/Promise/Preview + CTA templates, paragraph cap
> (`max_sentences_per_paragraph`, default 4), `min_h2_body_words` floors, and the 4
> `schema_version_effective` values (`1.7` / `1.7-no-context` / `1.7-degraded` /
> `1.7-legacy-h1`); **(2)** Brief Generator **v2.3**; **(3)** SIE; **(4)** Research &
> Citations v1.1.1; **(5)** Sources Cited v1.1; **(6)** Content Quality v1.0 (R1–R7);
> **(7)** Suite Architecture v1.0; **(8)** Engineering Implementation Spec v1.1.
> Satisfies Tier 1 (Writer PRD v1.7 + Engineering Spec) and Tier 2 #3/#4 (Brief Gen
> `intent_format_template`; Content Quality thresholds). **Still NOT in the repo**
> (accelerators, not blockers): Tier 2 #5 (3–5 real Writer outputs from
> AR-Internal-Tools `public.module_outputs`) and Tier 3 #6/#7 (Writer source-code
> pointer + production Anthropic model IDs) — grab the sample outputs if the
> documented `article_json` schema proves ambiguous against real rows.
>
> **Reconciliations to fold into §9 (from the verbatim PRDs + the live contract):**
> - **Writer model split is MIXED, not all-Sonnet** (corrects the §9.11 "Writer
>   model tier" row above): per §17, Title-gen + CTA + ICP-callout-judge use
>   **`claude-haiku-4-5`**; section / intro / FAQ / conclusion / Key-Takeaways /
>   brand-distillation+reconciliation use **`claude-sonnet-4-6`**. Degraded mode
>   (`no_citations` + no `client_context`) skips the brand calls (2,3) and the ICP
>   judge (10), so the port's hot calls are section(5)/intro(4)/FAQ(6)/
>   conclusion(7)/takeaways(9) on Sonnet + title(1)/CTA(8) on Haiku.
> - **Brief in the PRD is v2.3, but PRODUCTION runs v2.6** (see
>   `docs/blog-writer-live-contract.md`). The bundle's `intent_format_template` /
>   `format_directives` are the v2.3 spec; the live v2.6 brief output is ground
>   truth where they differ. M13 Brief Gen still synthesizes the brief, so this is a
>   reference-reconciliation, not a blocker.
> - **The Engineering Spec describes a 2-service topology** (platform-api
>   orchestrator + pipeline-api with 5 sibling modules, FastAPI `BackgroundTasks`,
>   `EXPECTED_MODULE_VERSIONS` validation). **We are NOT adopting that** — the
>   modules are ported in-process into our existing backend (handoff §9.1 / §9.6
>   decision stands). The spec is informational for the I/O contracts, not the infra.
> - **`no_citations` degraded path is first-class in v1.7** (`research.citations`
>   empty → continue, `no_citations: true`, sections written without grounding —
>   not an abort), exactly as §9.1 assumed.
> - **Live-contract schema corrections** (`docs/blog-writer-live-contract.md`,
>   recovered from the AR-Internal-Tools prod DB): real column names are
>   `module` / `input_payload` / `output_payload` (not `module_name` / `output_json`
>   — the Tier-2 #5 SQL sketch below still uses the old names); the writer `article`
>   is a **Markdown section array**, not an HTML blob; writer is **v1.7** as assumed.
>
> **Cross-check** the verbatim PRD against `docs/blog-writer-live-contract.md`; where
> they disagree, the live contract wins. **Next (per the 2026-06-12 re-sequence):**
> **M12 = SIE** (`docs/sie-module-plan.md`) → **M13 = Brief Generator**
> (`docs/brief-generator-module-plan.md`) → **M14 = Writer**
> (`docs/writer-module-plan.md`; port `backend/app/writer/` + adapter + `Generate
> now`). Bundle + live contract referenced from CLAUDE.md "Key file locations".

§9 was designed from a **conversation summary** of the AR Tools Blog Writer
PRD bundle, not from the PRDs themselves. ~~The source artifacts are NOT in
`docs/`.~~ **[Resolved 2026-06-12 — the bundle (`docs/blog-writer-pipeline-bundle.md`)
+ the live contract (`docs/blog-writer-live-contract.md`) are now in `docs/`; see the
status box above.]** The original fetch list below is **historical / superseded**,
retained for provenance:

**Tier 1 (blockers — required to start drafting M12):**
1. **Writer PRD #1, v1.7** verbatim. Must include:
   - Complete ordered step list (Step 1 → Step 10) with full descriptions
   - All section-call prompts (verbatim, not paraphrased)
   - JSON schema for Brief input
   - JSON schema for SIE input
   - JSON schema for `article_json` output
   - **§17 Call Inventory** (which step → Sonnet vs Haiku, max-tokens, retries)
   - Exact behavior of `schema_version_effective: "1.7-no-context"`
     (specifically what Steps 3.5a / 3.5b / 3.6 / 3.8 do when flipped off)
   - Exact behavior of `no_citations: true` (specifically Step 4F + §5.8.8)
   - Topic-adherence filter mechanic (LLM judge vs cosine vs both) + threshold
   - Agree / Promise / Preview intro template (verbatim)
   - CTA template / options
   - Paragraph-length cap (units + value)
   - Per-H2 body-length floor (units + value)
   - Banned-term regex hook spec
2. **Engineering Spec PRD** — JSON Schemas + module-to-module contracts.

**Tier 2 (gap-fillers — workable but risky without):**
3. **Brief Generator v2.3 `intent_format_template` table** — 8 rows
   (`intent_type` → `format_directives`). The adapter (§9.2) populates
   `brief.format_directives` from this lookup.
4. **Content Quality threshold values** if not already in 1.1.
5. **3–5 sample Writer outputs from AR-Internal-Tools Supabase** with
   matching Brief + SIE inputs (same `run_id`). SQL sketch:
   ```sql
   select r.id as run_id, r.keyword, r.intent_override,
          mo.module_name, mo.output_json, mo.cost_usd, mo.duration_ms, mo.attempt
     from public.runs r
     join public.module_outputs mo on mo.run_id = r.id
    where mo.status = 'complete'
      and r.id in (
        select run_id from public.module_outputs
         where module_name = 'writer' and status = 'complete'
         order by created_at desc limit 3
      )
    order by r.id, mo.module_name;
   ```
   These are ground truth — they win over the documented schemas if the two
   disagree (and they usually disagree).

**Tier 3 (huge accelerator):**
6. **AR-Internal-Tools Writer source code pointer** — repo URL + file paths
   + the entry function + Anthropic wrapper + prompt-template files. With
   these we port instead of re-implement.
7. **Anthropic model IDs in production** — exact `claude-sonnet-*` and
   `claude-haiku-*` strings used by the Writer service. Lets the M11 cost
   meter's `_LLM_RATES` reconcile.

**NOT needed** (modules skipped in v1):
- SIE PRD — flat `sie.terms.required[]` from supporting keywords; no
  entity extraction in v1 (deliberate; see handoff exchange 2026-06-10).
- Brief Generator full PRD beyond the `intent_format_template` table —
  we adapt at runtime, not port.
- Research & Citations PRD — `no_citations: true` short-circuits.
- Sources Cited PRD — same.
- Suite Architecture PRD — irrelevant when we run standalone.

**Procedure:** owner runs a separate chat with access to the bundle (likely
the AR-Internal-Tools repo / a Google Drive folder / the AR-Internal-Tools
Supabase). A self-contained fetch prompt was drafted in-session (2026-06-10);
the next session should expect the owner to paste back artifacts, then:
1. Drop them into `docs/` (e.g. `docs/blog-writer-prd-v1_7.md`,
   `docs/blog-writer-engineering-spec.md`, `docs/blog-writer-samples.md`).
2. Reference them from `CLAUDE.md` "Key file locations" + this file's §9.
3. Then start M12 drafting.

**One issue worth raising during M12 design:** with `clusters.h2_outline`
now empty at cluster level (2026-06-09 writer-ownership decision), the
adapter's `brief.heading_structure[]` will be thinner than the external
Writer PRD assumes — the Writer will have to generate body H2s itself,
possibly via a new step the external PRD didn't originally include.
