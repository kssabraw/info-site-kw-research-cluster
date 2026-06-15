# M13 — Brief Generator Module: Build Plan

**Status:** Draft for owner review (2026-06-12). Nothing built.
**Owner decision driving this plan (2026-06-12, in-session):** the **full Brief
Generator pipeline runs for every article, at write time only** — the same
lazy trigger rule as SIE. Rationale: **the process must be identical for every
article.** The M14 Writer's simplified 4-call adapter (intent / title+scope /
heading-structure / FAQs) is **superseded** — those were stand-ins for Brief
Gen Steps 3 / 3.5 / 4–8.7 / 10, and the real module now runs instead. Like
SIE, the Brief Generator is **never** invoked during keyword research/planning
(`/expand`, `/plan-articles`, `/regate`, `/fanout`, `/architecture` add no
hooks) and is never bulk-prefetched — it runs as a stage of generating a
specific article.

**Source of truth:** Brief Generator PRD v2.3 — PRD #2 in
`docs/blog-writer-pipeline-bundle.md` (lines ~2473–4232): Steps 0–12, output
schema, cost model, Python implementation notes (§12 reference code for the
gates/MMR), v2.1–v2.3 change notes.

**Sequence impact:** **M12 = SIE → M13 = Brief Generator (this plan) → M14 =
Writer → M15 = scheduling + link injection.** Brief Gen must precede the
Writer because the Writer's Input A *is* the Brief Gen's output — the native
module contract, no adaptation layer needed.

---

## 1. Provider audit — NO new services

Every candidate source the Brief Gen uses is billed through providers already
configured (verified against the PRD's own cost model, §9):

| Source | Provider | Status |
|---|---|---|
| Step 1 SERP scraping (top-20 headings/titles/metas + feature flags) | **DataForSEO SERP** (standard queue) | Already ours; expansion pipeline uses the same API |
| Step 2A PAA | **DataForSEO** | Already ours (`people_also_ask` exists in `dataforseo/client.py`) |
| Step 2B Reddit search | **DataForSEO Reddit search** | Same account; new endpoint wrapper |
| Step 2C Autocomplete + keyword suggestions | **DataForSEO** | Already ours (`autocomplete`, `keyword_suggestions` exist) |
| Step 2D LLM fan-out (ChatGPT / Claude / Gemini / Perplexity, parallel) | **DataForSEO LLM Responses** | Same account; new endpoint wrapper — **verify this product is enabled on our DataForSEO plan at build time** (it's a newer API family) |
| Step 5 embeddings | OpenAI **`text-embedding-3-large`** | Same key as our 3-small; see flag §7 #3 |
| LLM calls (title/scope, persona, scope verification, authority agent, FAQ pass, H3 parent-fit, intent-borderline) | Anthropic (already ours) | Sonnet/Haiku per call size, house client |

So the "no new third-party services" property that SIE gave up is **not**
further eroded by Brief Gen.

## 2. Scope — Steps 0–11 full; Step 12 flagged out

All of Steps 0–11 port as specified: input validation; SERP scrape; PAA /
Reddit / autocomplete / 4-LLM fan-out with `llm_fanout_consensus` tracking;
two-pass intent classification + `intent_format_template`; title + scope
statement (with the "does not cover" clause); subtopic aggregation (fuzzy
dedupe, source tagging); embedding gates (0.55 relevance floor / **0.78
restatement ceiling**); coverage graph + Louvain regions (seed=42); searcher-
persona gap questions; heading-priority formula (incl. the 0.20
information-gain weight); anchor-slot reservation; **MMR H2 selection** with
region-uniqueness + 0.75 anti-redundancy hard constraints (honest shortfall,
never padded); LLM scope verification; H3 selection (parent-relevance band
[0.65, 0.85], same-region, ≤2/H2) + parent-fit verification; **authority-gap
H3s** (3–5 SME topics competitors don't cover, displacement rules); FAQ
generation + intent gate; structure assembly + framing validator + title-case.

**Step 12 (silo cluster identification + viability checks) is skipped** —
this app already owns silo planning (M2–M5) at research time; running a
second silo discovery per article would duplicate and conflict. The
`discarded_headings` payload (with machine-readable discard reasons) **is
kept and persisted** — it's cheap, and it's the raw material for future
spin-off/coverage-gap intel. Flagged (§7 #1).

## 3. Write-time integration (`run_article_job` stage order)

Brief Gen and SIE are **independent** (both keyed on the article keyword,
neither consumes the other) — so they run **in parallel** as stage 1:

```
run_article_job(cluster):
  stage 1a: Brief Gen   (cache check → run on miss/stale)   ─┐ parallel
  stage 1b: SIE         (cache check → run on miss/stale)   ─┘
  stage 2:  Writer      (brief = Input A, sie = Input C, no_citations,
                         no client_context → "1.7-no-context")
  stage 3:  persist article_outputs   [M15 adds link_injector before serialize]
```

Wall time ≈ max(brief, sie) + writer ≈ **3–5 min/article**; the M15 worker's
concurrency cap of 3 still holds.

**Caching:** `fanout.briefs` mirrors `fanout.keyword_analyses` exactly —
keyed keyword + location_code, 7-day freshness, `force_refresh` writes a new
row, history preserved, **RLS on from day one** (service-role mediated +
owner read; same pattern/flag as the SIE cache). A regenerated article within
7 days reuses both caches and pays only Writer cost.

**Failure handling:** Brief Gen abort (e.g. `title_generation_failed` after
retries) fails the article run with the structured error — there is **no**
silent fallback to a thinner brief, per the owner's "process stays the same
for every article" rule. (The M14 Writer plan's adapter-stub fallback is
correspondingly demoted to dev/test fixtures only — flagged in §7 #2.)

## 4. What this dissolves in the Writer (M14) plan

- Adapter calls **A1–A4 are gone** (intent, title+scope, heading structure,
  FAQs — all now real Brief Gen output). The adapter shrinks to a thin
  field-mapper (Brief Gen output → Writer Input A is the native contract).
- Writer-plan **Δ1 and Δ2 dissolve** (the H2 gap and the title/scope contract
  — both were approximations of what Brief Gen now actually does).
- `clusters.adapter_cache` is no longer needed for brief content (superseded
  by `fanout.briefs`); drop it from the M14 migration.
- **H3s and authority-gap sections return** — the Writer's H3 handling
  (budget weight 1.2 for `authority_gap_sme`, stricter quality bar) is
  exercised from day one instead of being dormant.
- The Writer's `brief_schema_version: "2.0+"` expectation is natively
  satisfied (we emit v2.3).

## 5. Repo shape

`backend/app/briefgen/` — `models.py` (v2.3 output schema, pydantic),
`sources.py` (Step 1–2 DataForSEO wrappers: SERP-with-headings, PAA, Reddit,
autocomplete/suggestions, LLM-responses), `intent.py` (Step 3 two-pass +
template registry — shared with/migrated from the M14 writer `templates.py`),
`title.py` (Step 3.5), `graph.py` (Steps 4–5: aggregation, gates, networkx +
Louvain — the same libraries this app already uses for keyword clustering),
`persona.py` (Step 6), `select.py` (Steps 7–8.7: priority formula, anchor
reservation, MMR, H3 selection), `authority.py` (Step 9), `faq.py` (Steps
10–10.5), `assemble.py` (Step 11 + title-case), `pipeline.py` + `cache.py`.
Concurrency via `ContextThreadPoolExecutor` (the 4 LLM fan-outs + Reddit +
autocomplete run concurrently per the PRD); cost-metered under a new
**`brief_generation`** phase.

## 6. Cost & per-article totals

Brief Gen: **$0.37–$0.91/brief** (ceiling $1.00, PRD §9) — dominated by the
DataForSEO LLM-responses fan-out + the ~7 LLM call sites; DataForSEO data
endpoints are ~fractions of a cent. Updated per-article picture (first
generation, cache-miss):

| Stage | Cost | Time |
|---|---|---|
| Brief Gen | $0.37–$0.91 | ~1–3 min (parallel with SIE) |
| SIE | $0.30–$0.60 | ~1–3 min (parallel with brief) |
| Writer | $0.25–$0.45 | ~30–45 s |
| **Total** | **≈$0.92–$1.96** | **≈3–5 min** |

A 315-article session ≈ **$290–$620** of content-generation spend, incurred
per article at write time (lazy rule), spread across the drip window. M15's
`Schedule all` preview must include all three stages for uncached keywords —
at these numbers the $90 VA approval threshold trips at roughly a 50–100
article batch.

## 7. Sign-off decisions — ✅ RESOLVED 2026-06-15 (owner)

> **Owner sign-off 2026-06-15 — all six resolved (originals retained below for context):**
> 1. **Step 12 (silo identification) skipped — confirmed.** App owns silos;
>    `discarded_headings` persisted for future spin-off use.
> 2. **No degraded fallback brief — confirmed.** A Brief Gen abort FAILS the
>    article run (process-identical articles). The M14 stub survives only as a
>    test fixture.
> 3. ~~**`text-embedding-3-large` inside Brief Gen — exception GRANTED.**~~
>    **SUPERSEDED 2026-06-15:** the app-wide embeddings lock moved OpenAI →
>    **Google `gemini-embedding-001` @ 1536-dim** (whole-app owner override), so
>    Brief Gen uses Gemini like everything else — the 3-large carve-out is moot.
>    The selection gates (0.55/0.78/0.65/0.75) were calibrated for 3-large and
>    **must be recalibrated for Gemini** on live runs (tracked with the app-wide
>    threshold recalibration, not a Brief-Gen-only exception).
> 4. **Low-intent (<0.75) articles BLOCK — stricter path chosen.** An article with
>    intent confidence <0.75 does NOT auto-generate; it parks in an
>    `intent_review_required` state until an owner sets a manual intent override,
>    then generates. **Build impact:** needs a parked/blocked article state + a
>    manual-override API affordance (more than the proceed+warn alternative).
> 5. **Step 2 (v1.7 §5) reconstruction — accepted.** Fetch v1.7 §5 or 2–3
>    `briefs_cache` rows only if a build-time ambiguity surfaces.
> 6. **DataForSEO "LLM Responses" — ✅ ENABLED on our account (confirmed 2026-06-15).**
>    M13's Step-2D 4-LLM fan-out (ChatGPT/Claude/Gemini/Perplexity, ~$0.08–0.20/run)
>    runs as in production — no degraded path needed at launch; the bundle's
>    `llm_fanout_unavailable` graceful-degradation stays purely as a runtime safety
>    net for transient per-LLM failures.

### Original flagged list (now resolved)

1. **Step 12 skipped** (silo identification/viability) — this app owns silos;
   `discarded_headings` persisted for future spin-off use. Confirm.
2. **No degraded fallback brief in production** — a Brief Gen abort fails the
   article run (process-identical articles per your rule). The M14 stub path
   survives only as a test fixture. Confirm.
3. **`text-embedding-3-large` inside Brief Gen only** — the PRD's gates
   (0.55/0.78/0.65/0.75) are calibrated for 3-large; recalibrating to our
   3-small lock would trade known-good thresholds for consistency. Scoped
   exception to the app-wide 3-small lock. Confirm.
4. **`intent_review_required` handling** — the PRD flags low-confidence
   intent (<0.75) for human review; our write-time flow has no human in the
   loop. Proposed: proceed + WARN log + surface the flag on the article
   report (owner can regenerate with a manual intent override — small API
   affordance). Confirm.
5. **Step 2 sub-source specs reference Brief Gen v1.7 §5** ("operate
   identically to v1.7"), and the v1.7 document is **not in the bundle** —
   the 2A–2D mechanics here are reconstructed from the v2.x cost model,
   output schema, FAQ-step details, and concurrency notes (all consistent:
   everything is DataForSEO-sourced). If implementation hits ambiguity
   (e.g. exact Reddit query shape, LLM-responses request params), fetch v1.7
   §5 or 2–3 sample `briefs_cache` rows from AR-Internal-Tools as ground
   truth rather than guessing.
6. **Verify DataForSEO "LLM Responses" availability on our account** before
   M13 live validation (it's the one Step-2 endpoint family we haven't used;
   pricing ~$0.08–$0.20 per 4-LLM fan-out per the PRD).

## 8. Tests (sandbox-runnable)

The selection core is pure math over fixture embeddings: relevance floor /
restatement ceiling (0.55/0.78); Louvain region build (seed=42, deterministic);
region elimination rules; the 5-term priority formula incl. information-gain
tiers; anchor-slot reservation (region-uniqueness, 0.55 floor, unmatched-slot
logging); MMR with both hard constraints + honest-shortfall; H3 band [0.65,
0.85] + same-region + displacement-by-authority-gap; FAQ scoring tiers +
intent-gate relaxation; fuzzy dedupe (Levenshtein ≤0.15); structure assembly
ordering. LLM/DataForSEO wrappers mocked; one end-to-end fixture brief
asserted against the v2.3 output schema.

## 9. M13 acceptance

(1) Live brief on a real cluster keyword: top-20 SERP harvested; candidates
from ≥4 source families; gates/regions logged; title contains the keyword
with a "does not cover" scope clause; H2 skeleton obeys the intent template
(anchors present for templated intents); H3s within parent bands;
authority-gap H3s present; FAQs 3–5 and intent-gated; `discarded_headings`
populated with reasons. (2) Cache hit on second run within 7 days;
`force_refresh` writes a new row. (3) `brief_generation` phase in
`cost_breakdown`, total ≤ the $1.00 ceiling. (4) No Brief Gen execution
during `/expand`//`/plan-articles`/`/regate`/`/fanout`/`/architecture`
(code-inspection + log assertion). (5) Pure-module suite green; ruff clean.
