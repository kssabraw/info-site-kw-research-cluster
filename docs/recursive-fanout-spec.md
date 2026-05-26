# Recursive Fanout (RF) — spec

**Status:** spec / not built. Next milestone after M5 (re-sequenced ahead of the
PRD's M6 site-architecture step at the owner's direction). Implements **PRD §7.7**,
which exists only as a hardcoded `recursive_fanout: false` flag today.

Read `CLAUDE.md` and `docs/topic-fanout-prd-v1_7.md` §7.7 first. This doc is the
build plan; §7.7 is the source of truth where they conflict.

---

## 1. Why

M5 validation showed the *useful* keyword pool for a single seed tops out around
~900 active keywords → ~300 article candidates (direct mode), and that **deep
competitor mining of more silos doesn't help** — it adds raw volume the relevance
gate rejects as off-niche. The lever that genuinely grows the universe is going
*deeper*: each silo has sub-topics that, treated as their own seeds, surface a lot
of on-niche long-tail. That is recursive fanout, and it's the path to the
owner's "couple hundred substantial articles, knowledge-graph scale" goal.

## 2. What "done" looks like

- With `recursive_fanout: true`, after silo finalize the pipeline runs **one extra
  level deep per silo** before the relevance gate / clustering / planning.
- Each accepted silo yields sub-topics; expansion (and optionally mining) runs per
  sub-topic; the resulting keywords land under the parent silo (and, if Phase 2,
  under a persisted sub-silo).
- Depth is **hard-capped at 1** (no runaway recursion).
- Article volume rises materially over the non-recursive run on the same seed.
- The added cost is surfaced (cost estimate × the §7.7 multiplier) and guarded.

## 3. Design — two phases

RF can be staged. Build Phase 1 first; it captures most of the benefit at a
fraction of the cost/risk. Phase 2 only if depth-of-hierarchy is wanted.

### Phase 1 — deep expansion per silo (recommended first)
No sub-silo *discovery*. For each finalized silo, derive a handful of **sub-anchors**
and run the existing expansion (`keyword_ideas`, `keyword_suggestions`,
`query_fanouts`, PAA, autocomplete) on each, attaching results to that silo.

- **Sub-anchor source options** (decide during build): (a) an LLM call per silo
  asking for 4–8 distinct sub-topic phrases (cheap, on-niche); or (b) reuse the
  silo's top cluster representatives from a first non-recursive pass. (a) is
  cleaner and seed-agnostic.
- New keywords flow through the **existing relevance gate + Lever-3 routing +
  clustering** unchanged. No schema change required (optionally tag
  `sources += 'recursive'`).
- Competitor mining at this level is **off by default** (M5 finding: mining adds
  noise). Make it a flag.

### Phase 2 — full sub-silo discovery (§7.7 literal)
Per silo, run silo discovery (§7.1) to produce persisted **sub-silos**, then
expansion/mining/gate per sub-silo. Adds a real hierarchy (parent silo → sub-silos
→ articles). Higher cost + a data-model change (below). Only do this if the flat
Phase-1 output isn't structured enough.

## 4. Pipeline flow (Phase 1)

1. Finalize silos (unchanged).
2. **For each silo (parallel, bounded):** generate sub-anchors → run expansion on
   each → collect keywords for that silo.
3. Merge recursive keywords into the per-silo pool alongside the level-0 pool.
4. Relevance gate (+ peer filter + Lever-3 routing) — unchanged.
5. Clustering — unchanged.
6. Planning — direct mode or orchestrator — unchanged.

Runs in the **existing async job** (`app/jobs.py`); RF just adds a stage before
the gate. Reuse `run_expansion`; do **not** duplicate it.

## 5. Schema

- **Phase 1:** none required. Optional `keywords.sources` tag `'recursive'` for
  provenance/debug. Optionally a `sessions.recursion_level` for display.
- **Phase 2:** add `topics.parent_topic_id uuid null references topics(id)` and a
  `topics.depth int default 0`. Update RLS/queries that assume flat topics. The
  PRD §13 `topics` table is currently flat — this is the main structural cost of
  Phase 2.

## 6. Cost & guardrails

- **Cost multiplier 5×–8×** (§7.7). The cost estimate must multiply accordingly,
  and (per §8.4 / §11.3) a recursive run trips the approval gate for VAs — but the
  approval workflow is **M9 (unbuilt)**; for owner-direct runs, surface a cost
  warning and require an explicit confirm, don't silently spend.
- Depth cap **1**, enforced in code (a recursive sub-pass must not itself recurse).
- Reuse the **atomic run guard** (`try_mark_running`) and the **time/worker
  budgets** already in expansion; bound the per-silo sub-expansion concurrency.
- `recursive_fanout` is still wired to `false` in `create_session` — flip to a real
  setting and thread it into the job.

## 7. Reuse (don't rebuild)

- Expansion: `pipeline/expansion.py` (`run_expansion`, `build_anchor`).
- Gate + Lever 3 + peer filter: `run_relevance_gate(..., assign_best_silo=True,
  seed_terms, peer_terms)`.
- Clustering: `pipeline/clustering.py`.
- Planning: orchestrator or `direct=True` in `run_article_planning`.
- Sub-silo discovery (Phase 2): `pipeline/silo_discovery.py` (`run_silo_discovery`).

## 8. Open questions / decisions for kickoff

- Sub-anchor source: LLM sub-topics (rec.) vs. reuse first-pass representatives.
- Phase 1 only, or commit to Phase 2 hierarchy? (Affects schema.)
- Mining at the recursive level: default off (M5 finding) — confirm.
- Cost confirmation mechanics for owner-direct runs before M9 exists.
- Does direct mode become the default planner during RF? (Carried over from M5.)

## 9. Done-state checklist

- [ ] `recursive_fanout` is a real session setting, threaded into the async job.
- [ ] Per-silo sub-anchor generation (LLM or representatives), depth-capped at 1.
- [ ] Recursive expansion reuses `run_expansion`; keywords attach to the silo.
- [ ] Gate/Lever-3/clustering/planning run unchanged on the enlarged pool.
- [ ] Cost estimate reflects the 5–8× multiplier; owner confirm before spend.
- [ ] (Phase 2 only) `topics.parent_topic_id` + `depth`, RLS updated.
- [ ] Live-validated on `retatrutide`: materially more on-niche articles than the
      non-recursive run, peer noise still filtered.
- [ ] Tests for the recursive stage + depth cap.
