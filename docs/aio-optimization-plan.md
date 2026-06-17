# AIO (AI Overview) Optimization — Integration Plan & Working Notes

**Status:** Working notes / draft for owner review. Nothing built. Opened
2026-06-16 to capture a new body of research on optimizing content for Google's
AI Overview (AIO) and to track how it folds into the existing module plans.

**Source research:** owner-supplied (2026-06-16), reproduced verbatim in the
Appendix below so this doc is self-contained. Covers four things: §4.X
Decision-Fit Mapping, §4.X Max Cosine Synthesis (MCS), §13.X.8 Main-entity
derivation, and a drop-in Brief Generator PRD section (§X, AIO Heading
Optimization, schema v2.6 → 2.7).

**Relationship to existing plans:**
- `docs/brief-generator-module-plan.md` (M13) — receives the bulk of this work.
- `docs/writer-module-plan.md` (M14) — receives the decision-fit *rendering* +
  the deferred snippet directive.
- `docs/sie-module-plan.md` (M12) — **no new work**; only contributes its already
  locked spaCy `en_core_web_sm` dep, reused by entity derivation.

**Key fact established this session:** grep across all of `docs/` (PRD bundle,
all three module plans, live contract) returns **zero** matches for `AIO` /
`AI Overview` / `main_entity` / `Max Cosine` / `decision-fit`. This is a
**net-new feature area** — not a refinement of anything already specced.

---

## 0. Strategic direction — ANSWER-ENGINE-FIRST (owner decision 2026-06-17)

**The brief generator is being re-aimed: AIO + ChatGPT citation is the PRIMARY
optimization target; organic ranking is the floor, not the goal.** This
supersedes the "organic-first, AIO-as-additive-layer" framing that the rest of
this doc (§1–§5, written 2026-06-16) was built on. Where they conflict, this
section wins.

**Two owner decisions that set the architecture:**
1. **Embeddings (2026-06-17): dual/triple-space.** Gemini Embedding 2 for AIO
   proximity, OpenAI `text-embedding-3-large` for ChatGPT proximity *and* the
   eligibility gates. (Detail in §4 #1.)
2. **Selection model (2026-06-17): FULL MCS.** The organic priority/MMR/
   region/information-gain selection is **replaced** by Max Cosine Synthesis —
   generate a large candidate pool per heading slot, score by cosine to the
   answer-engine target(s), and climb (greedy/beam) to the set that collectively
   lands closest. Chosen with the evidence caveats in front of us (see below).

### Target architecture (answer-engine-first brief gen)

```
Step 1   SERP + AIO capture (X.1)  + ChatGPT answer promoted from the Step-2D
         LLM fan-out (already pulled today as a *source* → now a *target*)
Step 3.6 Main-entity derivation (X.2)            [stays 3-large; organic-side]
Step 5   ELIGIBILITY GATES become a PRE-FILTER, not selectors:
           - relevance floor (on-topic to keyword)        [3-large]
           - entity-stripped restatement ceiling (X.3)     [3-large]
         → produces the eligible candidate set MCS climbs within.
Step 7-8 H2 SKELETON — REPLACED by MCS: per slot, LLM generates a candidate
         pool (heading FORM = entity + one point, X.4 baked in at generation),
         each candidate scored in BOTH spaces, blended, beam-climb for coverage.
Step 8.7 H3s — ORGANIC, beneath each MCS-selected H2 (hybrid; see H3 decision):
         parent-band [0.65,0.85] + same-region + parent-fit LLM check, ≤2/H2,
         PLUS authority-gap H3s (3-5 SME topics competitors miss). NOT MCS;
         NOT form-enforced (H2-only). Where info-gain/differentiation re-enters.
Step 11  Form re-validation + title-case (residual safety).
Out      aio_insights + chatgpt_insights proximity readouts (now first-class,
         not advisory afterthoughts).
```

### Cross-space rule (critical, keeps the "never mix vectors" lock)

You **cannot** average a Gemini vector with a 3-large vector. So multi-target MCS
combines **scalar cosine scores, not vectors**: embed each candidate heading in
**both** spaces, score it against the AIO answer *in Gemini space* and the ChatGPT
answer *in 3-large space*, then blend the two **scalars**. Legal; never compares a
Gemini cosine threshold to a 3-large one.

### Sub-decisions — ✅ RESOLVED 2026-06-17 (owner, batch)

1. **Engine set — RESOLVED: AIO + ChatGPT only.** Targets = **Google AIO**
   (Gemini) + **ChatGPT** (3-large). Perplexity/Claude stay candidate *sources*.
2. **AIO vs ChatGPT weighting — RESOLVED: 0.5/0.5** blended score, eligibility =
   clears a floor on **at least one** engine. Recalibrate after X.6 has citation
   data.
3. **Candidate-pool cost — STILL OPEN (verification, not a decision).** Needs a
   real estimate before build (hundreds of candidates/slot × two embedding
   providers). *Default approach: bound the pool, cache per (keyword,location),
   meter under `brief_generation`.* → §6 / Section 2.
4. **Stopping rule / heading count — RESOLVED.** Climb until marginal cosine gain
   < ε **or** a max is hit; **floor = the intent template's required anchor slots**;
   cap ≈ **8–12 H2s**; **never pad** to hit a number (honest shortfall).
5. **Gates stay as eligibility pre-filter — RESOLVED** (on-topic + non-bare-
   restatement). The **0.20 information-gain weight is removed**; EMQ-stuffing
   avoidance is default.
6. **ChatGPT methodology — RESOLVED: accept the extrapolation, build both now;
   validate via X.6.** ChatGPT is promoted from a fan-out *source* to a *target* on
   the assumption the AIO playbook transfers (GPT-judged, Bing-retrieved). The X.6
   measurement loop is **extended to ChatGPT** to confirm/refute it on our data.
7. **H3 generation under MCS — RESOLVED 2026-06-17: HYBRID (the Section-1 item the
   first batch missed).** The full-MCS pivot replaced the H2 *selection* layer and
   removed the region/info-gain machinery the original H3 mechanism leaned on,
   leaving H3 *generation* under-specified. Resolution: **MCS owns the H2 skeleton;
   H3s are generated organically beneath each MCS-selected H2** —
   - **Regular H3s** (`select.py`, Step 8.7): parent-relevance band **[0.65, 0.85]**
     (cosine to parent H2), **same-region**, **≤2/H2**, + the parent-fit LLM check.
   - **Sub-choice RESOLVED: keep building the Step 4–5 coverage-graph + Louvain
     regions** purely to feed the H3 "same-region" constraint (cheap; keeps the
     original mechanism intact) rather than dropping regions.
   - **Authority-gap H3s** (`authority.py`, Step 9): unchanged — 3–5 SME topics
     competitors miss, displacement rules, `authority_gap_sme` tag.
     - **✅ RESOLVED 2026-06-17 (owner): authority gaps are H3s** — our v2.3 plan's
       level (`brief-generator-module-plan.md:57`), **not** the research's "Authority
       H2s (Step 9b)." Consequence: since H3 form enforcement is deferred, authority
       gaps are **NOT entity-form-enforced** → a **deliberate divergence from the
       research's X.4/X.9** ("Authority H2s (9b) MUST be entity-enforced"). Flagged.
     - **Why this is the *more* coherent choice (not just the conservative one):**
       authority-gap content is, by definition, *what competitors miss* — so it is
       **absent from the AIO answer** (which is synthesized from what ranking pages
       *do* cover). Form-enforcing it *toward* the AIO answer would be self-
       contradictory (you can't make "content nobody else has" close to the
       consensus answer). Leaving it as non-enforced H3s is exactly the
       answer-engine-first split: **H2s chase the consensus answer; H3s carry the
       differentiation that should *not* match it.**
     - **Rebase note:** if v2.6 prod places authority gaps at H2/Step-9b, the v2.6
       reconciliation must **map them down to H3** in our build.
   - **Why this matters:** authority-gap H3s are the **information-gain /
     differentiation we removed at the H2 level** (MCS pulls H2s *toward*
     consensus). H3s are where genuine differentiation re-enters — the guard
     against an all-proximity page being pure consensus-restatement.
   - H3 **form** enforcement stays **deferred** (H2-only, decision in the box
     below) — this decision is about H3 *selection/generation*, not phrasing.

> **Also resolved 2026-06-17 (defaults, no separate question):**
> - **Gemini task type** = `RETRIEVAL_DOCUMENT` for the AIO answer + `RETRIEVAL_QUERY`
>   for the heading (asymmetric retrieval); **not** `SEMANTIC_SIMILARITY` (the 06-16
>   culprit). Validate discrimination on a live run.
> - **H3 form enforcement** = deferred; **H2-only** this version (X.7 #3).
> - **v2.6 rebase** = *directive now, full plan-doc reconciliation at M13 build time*
>   (it's two milestones out; v2.6 details may shift). See §4 #2.
> - **AIO target TTL** = **shared 7-day brief cache** (owner chose simplest over the
>   shorter AIO-only refresh). **Accepted risk:** MCS may climb toward an AIO answer
>   that has since changed; `force_refresh` re-fetches, and revisit a shorter
>   AIO-only TTL if the X.6 loop shows staleness hurting citation. See X.7.

### Acknowledged risk (owner accepted)

- **Proximity is the research's LOW-confidence citation signal** — "necessary not
  sufficient"; closeness gets you *into contention* but link factors + stacking
  win the cite. Full-MCS selection bets the selection layer on it. The X.6
  measurement loop (now **required, not deferred**) is how we find out if it pays.
- **Organic is the entry ticket.** AIO/ChatGPT pull from the ranked/retrieved set;
  the eligibility gates + keeping pages in the top-20 set remain the floor that
  makes citation *possible* at all.

---

## 1. What this is

An **AI-Overview eligibility layer**. Both existing content modules (SIE, Brief
Gen) are tuned for *organic SERP* competitiveness (term modeling, coverage,
information gain). None of them try to get the page's text **lifted into Google's
AI Overview**. This research adds that: capture the live AIO answer, derive the
single main entity it repeats, and construct/enforce headings that sit close to
that answer in embedding space.

Two evidence levels — **NB: the §0 answer-engine-first pivot (2026-06-17)
overrides the "advisory/deferred" treatment of proximity below.** Original
framing retained for context:
- **Heading FORM** (entity + exactly one answer-derived point per heading) —
  **high confidence → hard rule.** (Unchanged; now baked into MCS candidate
  generation.)
- **Answer-engine PROXIMITY** (cosine scoring, MCS climbing) — low confidence as
  a *citation predictor*, but **per §0 it is now the PRIMARY selection driver**
  (owner accepted the risk; the X.6 loop is the check). No longer advisory.

---

## 2. Gap analysis — what's already in the plans vs. missing

| Research element | Lands on | Status | Note |
|---|---|---|---|
| §4.X Decision-Fit Mapping | Brief Gen (trigger/gating) + Writer (render) | ❌ Missing | Co-owned — see §3. |
| §4.X Max Cosine Synthesis (candidate-pool + greedy/beam cosine climb) | Brief Gen | ❌ Missing | **CORE per §0 (un-deferred 2026-06-17)** — now *replaces* organic selection, multi-target (AIO+ChatGPT). |
| X.1 AIO target capture (answer_text, cited_sources, fanout) | Brief Gen Step 1 | ❌ Missing | Plan's SERP scrape gets headings/titles/metas + feature flags, **not** the AIO block. Research claims it rides the existing depth-20 DataForSEO call — **verify DataForSEO returns the AIO block.** |
| §13.X.8 / X.2 Main-entity derivation (`entity.py`, new Step 3.6) | Brief Gen | ❌ Missing as a feature; ✅ deps already present | **spaCy `en_core_web_sm` already locked** (SIE §9, shared dep). **3-large already in Brief Gen** for the tie-break/sanity embeddings. Building blocks exist; module doesn't. Deterministic, no LLM in default path → free + testable. |
| X.3 Residual restatement gate (apply 0.78 ceiling to entity-stripped residual) | Brief Gen Step 5 (`graph.py`) | ⚠️ Partial | The **0.55 floor / 0.78 ceiling already exist**. This is a refinement (strip entity first), not a new gate. |
| X.4 Heading-form enforcement (entity + one point, every H2) | Brief Gen Step 11 framing (`assemble.py`) | ⚠️ Partial | The **framing validator + title-case stage already exists**. New rule rides its existing rewrite-and-re-embed path. The high-confidence core. |
| X.5 AIO proximity (+ ChatGPT) | Brief Gen assembly | ❌ Missing | **Promoted to first-class per §0** — drives MCS selection, not just a readout. |
| X.6 Measurement loop (post-publish AIO + ChatGPT citation + GSC) | Beyond M13 — needs publish telemetry | ❌ Missing entirely | **Now REQUIRED per §0** (validates the proximity-driven MCS bet, incl. ChatGPT), not a gate on a future "active mode." We have no published-article telemetry anywhere yet. |
| X.8 Schema 2.7 + metadata fields | Brief Gen | ❌ Missing | Implies the version rebase — see §4. |

**One-line summary:** ~85% net-new; almost all on Brief Gen (M13); **none on
SIE**; one piece (decision-fit render) on the Writer (M14). The *plumbing* (SERP
scrape, embedding gates, MMR/region selection, Step-11 framing, spaCy, 3-large)
already exists — the new work bolts onto those seams.

---

## 3. Ownership decision: Decision-Fit Mapping is CO-OWNED (corrected)

Initial take "it's a Writer item, not Brief Gen" was **wrong / oversimplified.**
Corrected split:

| Concern | Owner |
|---|---|
| Detect multi-answer query → tag section as decision-fit | **Brief Gen** (two-pass intent classification + `intent_format_template`, Step 3) |
| Reserve the section/H2 in `heading_structure` | **Brief Gen** |
| Supply branch conditions + overarching-default material | **Brief Gen** (persona gaps Step 6, PAA, Reddit) |
| Enforce pairing/gating rule (never standalone without a qualifying partner factor) | **Brief Gen** (structural co-occurrence check) |
| Emit a `format_directive` on the section | **Brief Gen** |
| Render the if/then branch prose + default statement | **Writer** |
| Validate branches distinct, condition-first, default present | **Writer** (validator sibling to Step 6.7) |

Pattern = brief-emits-directive / writer-enforces — the same one the research
itself uses for the Writer-side snippet rule. **Trigger + gating are brief-side;
only the rendered prose is writer-side.**

### 3.1 Detailed mechanism (end-to-end)

**Status:** design synthesized from the research requirements (Appendix §4.X) +
the ownership split above. **Not built.** The research gives requirements +
acceptance criteria, *not* an algorithm — so A1 (detector) and A5 (directive
schema) are decided-in-principle but spec-level; flagged in §6.

**When it fires.** Only on **multi-answer queries** — where the best answer
genuinely depends on reader context (comparisons, "best X for [different users]",
"should I…", "which X should I choose"). Secondary contributor; **never stands
alone** (A4). Complements MCS rather than duplicating it: **MCS optimizes the
heading set toward the consensus answer; decision-fit governs one section's *body*
content** to deliver conditional guidance — different levels.

**STAGE A — Brief Generator (M13): detect → reserve → source → gate → emit**

- **A1. Detect "multi-answer query?"** *(brief-side decided; detector to build.)*
  Extend the **Step 3** two-pass intent classifier (+ `intent_format_template`)
  with an LLM-judged flag: *does answering this well require branching by reader
  situation, and what are the candidate conditions?* Corroborate with intent shape
  (comparison/recommendation/decision), SERP/PAA signals, and whether the candidate
  subtopic pool splits into distinct reader segments. Output: boolean + candidate
  condition list.
- **A2. Reserve the decision-fit H2** *(decided; MCS-integration is the subtle bit.)*
  Reserve an H2 slot (e.g. *"Which [option] is right for your situation?"*) **via
  the existing anchor-slot reservation machinery, NOT a parallel system** (the
  §4.5-C collision). Under full-MCS: the decision-fit H2 is a **reserved anchor** —
  MCS does *not* drop it and fills only the *remaining* slots — but its **heading
  form is still enforced** (entity + one point, X.4). Selection forced, form
  enforced: exactly how templated-intent anchors already behave.
- **A3. Source the branch material** *(decided.)* The brief assembles raw material
  (not prose): the **branch conditions** (reader situations) + **condition→option**
  map + the **overarching default/priority statement**, drawn from **Step 6
  persona-gap questions**, **PAA**, and **Reddit**.
- **A4. Pairing/gating — "never standalone"** *(decided; structural check.)*
  Decision-fit underperforms alone and **must be paired**. Before emitting, run a
  **co-occurrence check** over the *selected* sections: is ≥1 qualifying partner
  factor present — **comparative depth**, **edge-case detail**, or **direct
  definitions**? No partner → don't emit (or add a partner first). Commercial/
  transactional pages may instead pair with **multiple-languages** or
  **direct-definitions**. ⚠️ **Spec gap:** that "Commercial Page Gating" rule is
  cross-referenced but **not in our research excerpt** — partner logic for
  commercial pages is under-specified; fetch the source before building A4.
- **A5. Emit the `format_directive`** *(decided; schema TBD.)* Attach a
  `format_directive` to the `heading_structure` section (metadata, not prose):
  render-as-decision-fit + the conditions + condition→option map + default + the
  "condition named first" requirement. Same pattern as the Writer-side snippet
  directive.

**STAGE B — Writer (M14, DEFERRED): render → validate**

- **B1. Render** the if/then prose: per condition, *"If you're [situation], choose
  [option]"* (**condition first, then action**), then the **overarching default**.
- **B2. Validate** (validator sibling to Writer **Step 6.7**, following the
  `min_h2_body_words` precedent): ≥1 branch + a stated default; branches mutually
  distinct, each a clear condition→action; condition stated first.

**Acceptance criteria** (research §4.X): multi-answer queries render ≥1 conditional
branch + stated default; branches mutually distinct (condition→action); section
never emitted standalone (A4 guarantees a partner factor).

**Pipeline placement (clarifies A1–A5 ordering vs brief steps).** The A1–A5
lettering is logical grouping, not step order. Actual order: **A1 detect at Step 3**
(intent time — SERP+PAA available, persona gaps not yet); **A3 source** completes at
**Step 6** (persona gaps); **A2 reserve / A4 gate / A5 emit** at **selection time
(Step 7–8)**, since the partner-factor co-occurrence check (A4) needs the selected
section set. The A1 flag + provisional conditions are produced early and enriched at
A3.

### 3.2 A1 detector — concrete spec ✅ (2026-06-17)

**Placement:** fold into the **Step 3** intent-classification call (it already has
query + SERP context; saves an LLM round-trip) — add the fields below to that call's
strict-tool-use output schema. Fallback: a dedicated **Haiku** call (short/
classification tier, house Anthropic client). **LLM-judged, not deterministic** —
acceptable (it shapes content, doesn't gate vectors); flagged.

**Inputs:** primary keyword/query; the intent label + `intent_format_template`;
top-N SERP titles/H2s (Step 1); PAA questions (Step 2).

**LLM task:** "Does answering this query well require *different* recommendations
depending on the reader's situation (vs one best answer)? If so, list the distinct
reader conditions that lead to different answers." Distinguish a *comparison the
reader still has to choose from* (decision-fit) from a *flat comparison* (that's the
`comparative_depth` partner factor, not decision-fit itself).

**Output contract:**
```
decision_fit_detection = {
  is_multi_answer:      bool,
  confidence:           float,   # 0–1
  candidate_conditions: [ { condition: str, distinguishing_factor: str } ],
  rationale:            str,
}
```

**Gate to proceed (reserve a section):** `is_multi_answer` **AND** `confidence ≥ τ`
(**propose τ = 0.7**, tunable) **AND** ≥ **2 distinct** `candidate_conditions` (after
dedup — one condition isn't a branch). Else: no decision-fit section.

**Deterministic corroboration (optional, adjusts confidence):** comparison/
recommendation/decision intent shapes bias up; PAA with conditional phrasing
("best … for", "which … if", "should I"); use-case-segmented listicle SERPs.

**Edge cases:** factual "what is X" → false; "X vs Y" → multi-answer *only if* the
choice depends on reader priorities (else it's `comparative_depth`); near-duplicate
conditions → dedup, drop if < 2 remain.

### 3.3 A5 `format_directive` schema — concrete spec ✅ (2026-06-17)

A **typed** directive (decision-fit is one `type`; the Writer-side snippet rule is
another) attached to the target `heading_structure` H2. Added as a pydantic model
under the **v2.7 schema bump (X.8)**; must satisfy `extra='forbid'`.

```
format_directive = {
  type:              "decision_fit",          # discriminator
  section_id:        <ref to the reserved H2 in heading_structure>,
  branches: [
    { condition: str,                          # reader situation (rendered FIRST)
      option:    str,                          # recommended action for that condition
      source:    "persona_gap"|"paa"|"reddit"|"llm" },   # provenance (A3)
    ...                                        # ≥ 2, mutually distinct
  ],
  default_statement: str,                       # priority holding across branches
  partner_factor:    "comparative_depth"|"edge_case_detail"|"direct_definitions"
                     |"multiple_languages",     # WHICH partner satisfied A4 (must be present)
  constraints: { condition_first: true, min_branches: 2, distinct_branches: true },
  detector:    { confidence: float, rationale: str },   # A1 audit echo
}
```

Carries everything the Writer needs to **render (B1)** and the validator to **check
(B2)**, plus the A4 gate result (`partner_factor` — *which* partner is present, not
just that one is) and the A1 audit echo. `branches[].source` keeps per-condition
provenance, consistent with the brief's general provenance practice.

### 3.4 Open: Commercial Page Gating (A4 commercial partner logic)

⚠️ **STILL BLOCKED — needs the source.** The research's §4.X cross-references a
**"Commercial Page Gating"** section (for transactional/commercial pages,
decision-fit may pair with `multiple_languages` or `direct_definitions`) that is
**not in the excerpt we hold**. A4's commercial-page branch can't be specced without
it. → Owner to supply that section (or confirm we defer commercial-page decision-fit
and gate only on the three general partners: comparative-depth / edge-case /
direct-definitions). Tracked in §6.

---

## 4. Open conflicts to resolve before this slots in

1. **Gemini vs OpenAI embeddings — ✅ RESOLVED 2026-06-17 (owner): DUAL-SPACE.**
   Background: MCS (§4.X) says "MUST be Gemini (Vertex)"; the drop-in PRD §X.5/X.7
   walks it back to "3-large only, no Gemini track." We **rolled Gemini back
   app-wide 2026-06-16** (poor write-time relevance discrimination) and are locked
   on OpenAI `text-embedding-3-small` app-wide / `3-large` inside Brief Gen.
   **Owner decision (2026-06-17): use Gemini Embedding 2 for the AIO-proximity path
   ONLY**, keeping `text-embedding-3-large` for every organic gate + entity
   derivation. Rationale: proximity is about matching Google's AIO judging model
   (Gemini), so Gemini is the *right* model there; the organic gates are where
   Gemini just failed, so they stay 3-large.
   - **This OVERRIDES PRD §X.5's "3-large only, no second model" stance** — a
     deliberate, scoped divergence (flagged).
   - **Vector-space safety holds** *because the proximity score is non-gating and
     self-contained*: `cosine(heading, aio_answer)` is computed entirely in Gemini
     space and **never compared to any 3-large gate value**. Two isolated spaces,
     not a mixed one — the CLAUDE.md "never mix vector spaces" lock is respected so
     long as no Gemini cosine is ever compared against a 3-large cosine.
   - **Implementation notes / open items:**
     - Entity derivation (X.2): tie-break + the 0.45 keyword sanity check **stay
       3-large** (they feed organic selection, not AIO matching).
     - Brief Gen must invoke the **dormant `GeminiEmbedder` directly** for the
       proximity path, independent of the global `EMBEDDING_PROVIDER=openai` (which
       stays OpenAI). `GEMINI_API_KEY` already provisioned (from the 06-15 cutover).
     - **Gemini task type is an open decision** — `SEMANTIC_SIMILARITY` was the
       suspected culprit in the 06-16 gate failure; **now matters MORE** because
       (per §0) proximity *drives MCS selection*, not just a readout. Pick
       deliberately (try `RETRIEVAL_*`); validate discrimination before trusting it.
     - **Cost is no longer small** (per §0): MCS embeds *hundreds of candidates per
       slot* in Gemini (AIO) **and** 3-large (ChatGPT). Bound the pool + cache;
       meter under `brief_generation`. Needs a real estimate before build.
     - **No gate recalibration needed** (the 3-large eligibility gates never touch
       Gemini; Gemini only scores AIO proximity).
2. **Version + module-name mismatch.** Research is written against **prod v2.6 →
   2.7** with prod filenames (`dataforseo.py`, `parsers.py`, `entity.py`,
   `graph.py`, `framing.py`, `assembly.py`). Our M13 plan targets **v2.3** with a
   different layout (`sources.py`, `intent.py`, `graph.py`, `select.py`,
   `authority.py`, `faq.py`, `assemble.py`). Per `blog-writer-live-contract.md`,
   **prod v2.6 wins over PRD v2.3.** → **RESOLVED 2026-06-17 (owner): target v2.6
   as a directive now; do the full plan-doc reconciliation (filenames, schema,
   `EXPECTED_MODULE_VERSIONS`) when M13 build actually starts** — it's two
   milestones out and v2.6 details may shift, so don't churn the plan early.
3. **X.7 "Research-enrichment propagation" flag — likely N/A for us, but verify.**
   It worries a *Research* stage prefers its own enriched `heading_structure`,
   voiding brief-side entity enforcement. Our Writer consumes
   `brief.heading_structure[]` directly (`writer-module-plan.md:74`); we have no
   Research-re-touches-headings stage. → Probably N/A, but **confirm the Writer
   never re-derives headings** before relying on brief-side enforcement holding.

---

## 4.5 Collision analysis — does this collide with the current brief generator?

**Scope note.** "Current brief generator" is ambiguous: our **M13 plan targets
v2.3** (not built); **prod runs v2.6** (live contract). The research is written
against v2.6 → 2.7. The collisions below are against *mechanisms both versions
share*, except #D which is plan-level.

**Headline — NB: §0 (2026-06-17) reframes this section.** As *originally* written,
the safe path was the curated PRD §X (additive capture, post-gate form enforcement,
non-gating proximity), and collisions (B) MCS-as-selection / (C) Gemini were things
to avoid. **§0 deliberately adopted both (B) and (C)** — full MCS selection + Gemini
for AIO proximity — and resolved their collisions (objective-flip for B; dual-space
scalar-blend for C; see §4.5-B and §4 #1). So of the original three, only **(A) the
X.3→X.4 implementation ordering** remains a live "don't get it wrong." The analysis
below is kept as the reasoning trail.

> **Partly superseded by §0 (2026-06-17):** MMR is *removed* in the full-MCS
> design, so its 0.75 anti-redundancy guard no longer exists — MCS's own "set
> coverage" climbing replaces it. The restatement ceiling survives as a
> **pre-filter** (X.3), so the entity-stripping/ordering point below still holds.

### A. THE one that bites: entity-in-every-heading vs. the redundancy/restatement math

Two existing mechanisms exist specifically to *suppress* near-duplicate headings:
- the **0.78 restatement ceiling** (Step 5 gate), and
- the **0.75 anti-redundancy hard constraint** inside MMR (Step 8).

X.4's rule (*every H2 = main entity + one point*) prepends the **same entity token
to every heading**, mechanically inflating pairwise heading cosine — exactly the
signal those two constraints reject. Naive implementation = entity enforcement
fights the redundancy guards (headings gated out, or MMR treats them as redundant
and won't select them).

**Resolved by ordering — and this is the part you cannot get wrong:**
- **X.3** strips the entity off the residual *before* the 0.78 ceiling (judges the
  differentiated point, not the shared entity).
- **X.4** applies the entity *post-selection*, at Step 11 framing — so MMR and the
  restatement gate never see the entity-bearing form.

→ Collision avoided **only** if implemented in sequence: derive at 3.6 → gate on
residual at 5 → enforce form at 11. Wrong order breaks the selection math.

### B. MCS-as-selection + Gemini — REVERSED by §0: now ADOPTED, not rejected

> **Superseded by §0 (2026-06-17):** this subsection argued to *reject*
> MCS-as-selection. The owner has since chosen **full MCS selection** + Gemini for
> AIO proximity. So conflict #1 is resolved by *flipping the objective* (info-gain
> removed; answer-proximity is now the goal), and conflict #2 by the **dual-space
> scalar-blend** (§0 cross-space rule) — Gemini and 3-large cosines are blended as
> scalars, never compared as a single space. The original analysis is kept below
> for the reasoning trail.

Raw **§4.X MCS** says to *select* headings via "greedy/beam monotonic climbing"
toward the AIO answer. Taken literally this **replaces the current selection
architecture** — fights MMR, the 5-term priority formula, the **0.20
information-gain weight**, and Louvain region-uniqueness head-on. Two hard
conflicts:
1. **Selection objective:** cosine-climb-to-AIO vs. information-gain/coverage —
   opposite directions (the research itself admits "active proximity mode… opposes
   the information-gain weight").
2. **Embedding model:** §4.X says proximity "MUST be Gemini (Vertex)." Collides
   with TWO things — brief gen runs **`text-embedding-3-large`**, and CLAUDE.md
   hard-locks ***"Vector spaces must never be mixed across providers/models."*** A
   Gemini score compared against 3-large selection is an illegal cross-space
   comparison. (We also **rolled Gemini back 2026-06-16**.)

→ PRD §X neutralizes conflict #1 (selection objective): keeps organic selection
**intact** and demotes proximity to a **non-gating side-channel**. **Adopt §X's
framing for selection, not §4.X's literal "climb-to-AIO" one.** On conflict #2
(embedding model): **owner override 2026-06-17 (§4 #1)** — Gemini Embedding 2 IS
used, but **only** in the non-gating proximity path, in an isolated space never
compared to the 3-large gates. So §4.X's "must be Gemini" is honored *for
proximity*; the gates stay 3-large. The collision is dissolved by the dual-space
split, not by rejecting Gemini outright.

### C. Controlled collisions (designed regression-safe)

- **X.3 modifies Step 5** (existing gate) but is byte-identical for entity-absent
  candidates ("entity-free briefs produce byte-identical Step 5 output").
- **X.4 rides the existing Step 11 framing rewrite path** (composes, doesn't
  replace). **The "do authority H2s inherit the form rule?" worry is now MOOT**
  (resolved 2026-06-17, §0 #7): authority gaps are **H3s**, and H3 form enforcement
  is deferred — they are deliberately *not* entity-enforced, so there is no
  authority-H2 enforcement path to verify. (X.4 enforcement applies only to the
  MCS-built H2 skeleton.)
- **Anchor-slot reservation:** decision-fit mapping wants a *guaranteed* section,
  but MMR only selects what scores well. A reserved decision-fit slot must
  integrate with the **existing anchor-slot reservation** (intent-template
  machinery), not bolt on beside it — else two competing reservation systems.
- **EMQ vs. main-entity:** title generation (3.5) puts the keyword (EMQ) in the
  title; the form rule wants the main-entity (which may ≠ EMQ) in every heading.
  Managed by the `emq_identical` flag + per-SERP softening; minor.

### D. Plan-level collision

The research assumes **v2.6** filenames/schema (`framing.py`, `assembly.py`,
`parsers.py`, `extra='forbid'`, `EXPECTED_MODULE_VERSIONS`). Our M13 plan is
**v2.3** with a different layout. Live contract: **prod v2.6 wins** → integrating
realistically means **rebasing M13 onto v2.6 first** (same as §4 #2). Not a runtime
collision, but a collision between this research and the *current written plan*.

---

## 5. Proposed slicing — RE-SLICED for answer-engine-first (§0)

The original organic-first slicing (ship form, defer MCS) **no longer applies** —
MCS *is* the selection layer now, so it can't be deferred. New slicing:

**Core (the answer-engine-first build):**
- X.1 AIO target capture (Step 1) + **promote the Step-2D ChatGPT answer to a
  target** — pending the "does DataForSEO return the AIO block?" verification.
- Eligibility gates as a **pre-filter** (relevance floor + entity-stripped
  restatement ceiling, X.3) — 3-large; info-gain weight removed.
- **MCS multi-target selection** (§4.X) — candidate-pool generation with the
  entity+one-point form (X.4) baked in, dual-space scalar-blended scoring
  (Gemini AIO + 3-large ChatGPT), beam-climb for set coverage. **The centerpiece.**
- X.2 Main-entity derivation (Step 3.6, `entity.py`) — feeds form + the residual
  gate; 3-large.
- X.6 measurement loop — **now REQUIRED** (the only validation that proximity-driven
  selection actually earns citations; extend it to ChatGPT, §0 sub-decision #6).
- X.8 metadata + schema bump (gated on the v2.6 rebase, §4 #2).

**Still genuinely deferred:**
- Decision-fit **rendering + validator** (Writer / M14).
- Writer-side extractable-snippet directive (separate spec, M14).

**Pre-build blockers (must resolve before code):** — the §0 decision batch
(2026-06-17) cleared the design forks; what remains is **verifications**, not
decisions (see §6):
- A real **MCS cost estimate** (the one open Section-1 item — materially pricier
  than today's selection; candidate-pool bound depends on it).
- **DataForSEO AIO-block availability** on the depth-20 SERP call.
- The **v2.6 plan-doc reconciliation** — directive locked (§4 #2); the detailed
  filename/schema mapping happens at M13 build start, not now.

---

## 6. Next actions (not yet done)

**Section-1 decisions — ✅ all RESOLVED 2026-06-17** (see §0 sub-decisions + §4):
embeddings (dual/triple-space), v2.6 rebase (directive-now), engine set (AIO +
ChatGPT), weighting (0.5/0.5), stopping rule, Gemini task type (`RETRIEVAL_*`),
AIO TTL (shared 7-day), **H3 generation = HYBRID** (§0 #7; H3 *form* enforcement
deferred — distinct things), gates-as-pre-filter, ChatGPT (accept + validate via
X.6). **Remaining = the Section-2 verifications/spikes + the build.**

- [ ] **MCS cost estimate** — the one open Section-1 item that's really a
      verification (hundreds of candidates/slot × two embedding providers).
- [ ] Verify DataForSEO surfaces the AIO block on the depth-20 SERP call.
- [ ] Confirm the Writer never re-derives headings (X.7 propagation N/A check).
- [ ] **At the v2.6 rebase: map authority gaps to H3** (resolved 2026-06-17, §0 #7
      — authority gaps are H3s, deliberately not entity-form-enforced). If v2.6 prod
      places them at H2/Step-9b, move them down. *(The earlier "verify Step 9b
      framing rule set" check is moot — there is no authority-H2 enforcement path.)*
- [ ] **Enforce the X.3→X.4 implementation ordering** (derive 3.6 → residual gate
      5 → form enforce 11) so entity tokens never reach MMR/the restatement ceiling
      (collision §4.5-A). Add a regression test: entity-free brief = byte-identical
      Step 5 + Step 11 output.
- [x] **Decision-fit A1 detector** — specced in §3.2 (Step-3 fold-in, output
      contract, τ=0.7 gate, ≥2 distinct conditions). 2026-06-17.
- [x] **Decision-fit A5 `format_directive` schema** — specced in §3.3 (typed
      directive, branches+default+partner_factor+detector echo). 2026-06-17.
- [ ] **Commercial Page Gating (§3.4)** — STILL BLOCKED on the source: the research
      cross-references it but it's not in our excerpt. Owner to supply the section,
      or confirm we defer commercial-page decision-fit and gate only on the three
      general partner factors.
- [ ] Once signed off: write the concrete Brief Gen addendum mapping §5 ship-now
      slice onto the (rebased) file layout, with pure-module tests per §13.X.8 /
      X.9 acceptance.

---

## Appendix — Source research (verbatim, owner-supplied 2026-06-16)

### 4.X Decision-Fit Mapping

**Purpose.** Increase AIO eligibility and on-page helpfulness by giving the reader
conditional, situation-specific guidance rather than a single flat answer.

**Definition.** Decision-fit mapping is content that routes the reader to the
option matching their situation using if/then branching, anchored by an overall
priority that holds across branches (e.g., "If X, do A. If Y, do B. Either way,
the key thing is Z."). Carried over from the prior organic-ranking study, where it
was the top factor; here it is a secondary contributor.

**Writer requirements.**
- Where a query has multiple valid answers depending on the reader's context, the
  writer MUST present them as explicit conditional branches ("if you're
  [situation], choose [option]"), not as one averaged recommendation.
- Each branch SHOULD name the triggering condition first, then the recommended
  action.
- The section MUST include an overarching default or priority statement that
  applies regardless of branch.
- This factor MUST be paired — it underperforms alone. Co-deploy with at least one
  of: comparative depth, edge-case detail, or direct definitions.
- For transactional/commercial pages, decision-fit mapping MAY serve as the unlock
  partner alongside multiple-languages or direct definitions (see §[Commercial
  Page Gating]).

**Acceptance criteria.**
- Multi-answer queries render ≥1 conditional branch structure plus a stated
  default.
- Branches are mutually distinct and each maps a clear reader condition to a clear
  action.
- Section is never emitted as a standalone block without a qualifying partner
  factor present on the page.

### 4.X Max Cosine Synthesis (MCS) — Heading Construction

**Purpose.** Construct the page's heading set (title, H1, H2s) to sit as close as
possible in embedding space to Google's live AIO answer, maximizing eligibility to
be the text lifted into the AI Overview.

**Definition.** Max Cosine Synthesis scores candidate headings by cosine
similarity (0–100) to the target AIO answer and assembles the set that
collectively lands closest. Max cosine = maximize each heading's closeness;
synthesis = optimize the set for coverage, not any single heading. Embeddings MUST
be generated with Gemini (Vertex) embeddings to match the model judging AIO/AI
Mode.

**Heading formula.** Every title, H1, and H2 = main entity + one specific point
the AIO answer actually makes, in that order.
- Main entity = the noun phrase the AIO answer repeats — not necessarily the
  exact-match query (EMQ).
- The appended point MUST be a claim the answer actually states (e.g., "encourages
  positive transformation"), never a bare topic word ("meaning," "love").
- Exactly one point per heading — combining points lowers cosine.

**Writer/system requirements.**
- The system MUST fetch the live AIO answer for the target query and use it as the
  scoring target ("bull's-eye").
- The system MUST generate a candidate pool (hundreds) per heading slot, score
  each by cosine to the target, and select via greedy/beam monotonic climbing —
  keep closest, generate variations around winners, rescore, retain only
  improvements, repeat to diminishing returns.
- Selection MUST favor set coverage: prefer headings that add closeness the
  existing set lacks, so the set spreads across the answer's distinct points.
- The main entity MUST appear in every heading slot (title, H1, all H2s).
- The system MUST NOT stuff the EMQ into H1/H2s unless competitors universally do;
  EMQ stuffing is an accepted organic-ranking demotion traded for AIO reach (AIO
  pulls from as deep as position 20).
- Fan-out sub-questions MAY be used as supplementary targets; cosine self-filters
  tangential ones, so coverage does not dilute relevance.
- Target ceiling: optimize toward 95–96 (the natural-heading asymptote). Do not
  chase 100 (achievable only by reproducing the answer).

**Acceptance criteria.**
- Every heading matches the formula (entity present, exactly one answer-derived
  point, no bare topic words).
- Each heading's cosine to the AIO target is reported; set mean clears the
  competitor baseline (~71 observed) with target individual scores ≥90.
- No heading exceeds one point; no heading omits the main entity.

**Note (evidence level).** High confidence as a qualifying/heading-construction
method — the mechanism (cosine on matched-model embeddings) is sound and the
formula is testable. Lower confidence as a citation predictor: in the same study,
closeness strongly relates to being on-topic/in-contention but barely predicts
which on-topic page wins the citation — that decision appears driven by link
factors and combination stacking. Treat MCS as necessary-not-sufficient: it gets
the page into the field; pair with the link catalyst and the Fantastic Four stack
for citation. Specific figures (86/91/95 progression, ~71 baseline, ~20-pt edge)
are from a small single-operator study with noted scraper limitations —
directional, flag for live validation.

### 13.X.8 Main-entity derivation (entity.py)

**Purpose.** Derive the single main entity — the noun phrase the AIO answer
repeatedly names, in its preferred surface form — for use by the heading-form pass
(13.X.7), the residual restatement gate, and MCS-style rephrase suggestions
(13.X.4).

**Inputs.** aio_target (when present), generated title (Step 3.5), primary
keyword. Output: main_entity = { canonical: str, variants: [str], source: "aio" |
"title_fallback", confidence: float, multi_entity_flag: bool } — persisted on the
brief.

**Derivation (AIO present)**
- Candidate extraction. Run noun-phrase chunking over answer_text (spaCy
  en_core_web_sm noun_chunks is sufficient; no new provider). Strip leading
  determiners/possessives ("the", "a", "your") and trailing punctuation from each
  chunk.
- Normalization for counting (not for output). Lowercase; lemmatize the head noun
  only (so "crystals"/"crystal" merge but "angel number 327" isn't mangled);
  collapse whitespace. Build a map normalized-form → list of raw surface forms with
  counts.
- Variant clustering. Merge normalized forms that are token-set equal or where one
  is a strict superstring of the other with the same head noun ("angel number 327"
  ⊇ "number 327"; "327 angel number" token-set-equals "angel number 327"). Each
  cluster's count = sum of member counts.
- Scoring. For each cluster: score = frequency × subject_weight × specificity.
  - frequency: total mentions across the answer.
  - subject_weight: 1.5× for mentions appearing as grammatical subject of a
    sentence (the answer is about it, not merely mentioning it). Dependency parse
    gives this free with spaCy.
  - specificity: 0.5× penalty for single-token generic heads with no modifier
    ("number", "design", "benefits") — kills the failure mode where a generic word
    out-frequencies the real entity.
- Pronoun chains ("it", "they") are not candidates but do add +1 frequency to the
  cluster they corefer to when resolution is unambiguous (nearest preceding
  subject); skip coreference entirely if ambiguous — it's an accuracy bonus, not a
  dependency.
- Canonical surface form. From the winning cluster, emit the most frequent raw
  surface form (capitalization and word order as the answer wrote it). This is the
  string composed into headings. All other members go to variants (used by
  13.X.7's fuzzy entity-span detection, so a heading containing any variant counts
  as entity-bearing).

**Confidence gate and fallbacks**
- Confidence = winning cluster score ÷ runner-up score.
  - ≥ 1.5 → accept, source: "aio", confidence recorded.
  - < 1.5 → set multi_entity_flag: true, then tie-break by title alignment: pick
    the candidate with higher cosine (3-large) to the generated title. If still
    within 10%, fall through to title fallback. (Multi-entity AIO answers are real
    — comparison queries like "X vs Y" legitimately have two. Composing the wrong
    one into every heading is worse than falling back.)
- Sanity check (always, even at high confidence). Winning entity must have cosine ≥
  0.45 to the primary keyword embedding. Below that, the AIO answer is probably
  tangential or the SERP is mis-fetched — fall back. This is the guard against
  enforcing a hallucinated/off-topic entity pipeline-wide.
- Title fallback (source: "title_fallback", used when AIO absent, low-confidence
  tie, or sanity-check failure): noun-phrase chunk the generated title, take the
  chunk with highest cosine to the primary keyword. Title fallback always exists by
  construction (Step 3.5 titles contain the keyword), so derivation can never
  hard-fail — main_entity is always populated and the heading-form pass is never
  skipped.

**Edge cases (explicit behavior)**
- "X vs Y" / comparison intents: expected low-confidence path; tie-break by title
  usually resolves to whichever the article centers. If the intent template is
  comparison-shaped, allow either entity to satisfy the per-heading entity
  requirement (13.X.7 check accepts canonical ∪ variants ∪ secondary_entity).
  Record secondary_entity when multi_entity_flag is set.
- EMQ-identical entity: when canonical == primary keyword (e.g. "iGaming design"),
  that's allowed — the study's position is you take the EMQ-stuffing demotion
  knowingly for AIO reach. Emit emq_identical: true so the per-SERP switch (end of
  13.X.7) can soften enforcement on non-AIO SERPs.
- Very short AIO answers (<3 sentences): frequency signal is unreliable below ~3
  mentions; if winning frequency < 3, treat as low-confidence regardless of ratio.
- Brand/site names in the answer: excluded as candidates (match against
  cited_sources domains and an org-NER tag) — the answer naming "Healthline"
  repeatedly doesn't make Healthline your entity.

**Tests (pure, fixture-runnable)**
Fixture answers asserting: (a) "327 angel number" query → canonical "angel number
327" with the query form in variants; (b) generic-head suppression ("benefits"
never beats "magnesium glycinate benefits"); (c) comparison answer triggers
multi_entity_flag + correct title tie-break; (d) sub-0.45 sanity failure falls
back to title; (e) AIO-absent brief produces source: "title_fallback"
deterministically; (f) brand exclusion; (g) determinism — same input, same output
(no LLM in the default path, so this is free).

**Cost.** Zero marginal API spend in the default path — spaCy is local, the only
embedding calls (tie-break, sanity check) are 2–3 vectors against keys you already
hold. An optional LLM adjudication for the multi_entity_flag path could be added
later, but the deterministic version should ship first precisely because it's
testable and free.

### PRD §X — AIO Heading Optimization

Drop-in section, written against the as-built pipeline (v2.6 → bumps to 2.7) and
existing conventions — step labels, filenames, side-channel pattern, echoed
metadata, extra='forbid'. Headings-only; the Writer-side snippet directive is
cross-referenced but out of scope.

**Status:** Draft for owner review. Schema: bumps SCHEMA_VERSION 2.6 → 2.7 (new
response fields under extra='forbid'; EXPECTED_MODULE_VERSIONS["brief"] must move
in lockstep). Module: writer/pipeline-api/modules/brief/.

**Goal.** Make headings eligible to be lifted into Google's AI Overview by
enforcing the validated heading form from the AIO study — main entity + one
specific point, in every H2 — while leaving organic-tuned selection (relevance
floor, restatement ceiling, MMR, regions, intent templates) intact. AIO proximity
scoring is captured as advisory observability only; it does not gate.

**Design principle.** Enforce the heading form (high-confidence, validated). Do not
make AIO-answer proximity a selection driver (low-confidence; the source study's
own retrospective found proximity barely separates citation winners among on-topic
pages). Form is a hard rule; proximity is a reported side-channel.

**X.1 New: AIO target capture (Steps 1–2 — dataforseo.py, parsers.py)**
- The SERP parse MUST extract the AI Overview block when present: aio_target = {
  present: bool, answer_text, cited_sources[], fanout_questions[], fetched_at }.
- Modeled on the v2.6 blind-spot side-channels: observability-only, never gates,
  degrades to available=False. AIO absence MUST NOT abort or alter any existing
  path. No new provider — rides the existing depth-20 SERP call.

**X.2 New: Main-entity derivation (Step 3.6 — entity.py)**
- Runs after Step 3.5 (needs title for fallback), before Step 4 pass-1 / Step 5
  (consumed by the residual gate). Deterministic; local spaCy + 2–3 embeddings via
  the existing OpenAI key. MUST NOT hard-abort.
- Derives the noun phrase the AIO answer repeats (frequency × subject-weight ×
  specificity over normalized noun chunks), emitting the canonical surface form
  (answer's capitalization/word order). Output: main_entity { canonical,
  variants[], secondary_entity, source: "aio"|"title_fallback", confidence,
  multi_entity_flag }.
- Confidence gate: winner/runner-up ratio ≥ 1.5 accepts; below → multi_entity_flag,
  tie-break by title cosine. Sanity: entity must be ≥ 0.45 cosine to the keyword or
  fall back. Fallback (AIO absent, low confidence, or sanity fail):
  highest-keyword-cosine noun chunk of the title. Fallback always exists, so
  main_entity is always populated.
- main_entity ≠ EMQ: when canonical == keyword, emit emq_identical: true (feeds the
  per-SERP softening in X.5).

**X.3 Refined: residual restatement gate (Step 5 — graph.py, embed_with_gates)**
- The relevance floor applies to the full candidate embedding (unchanged).
- The restatement ceiling applies to the entity-stripped residual for candidates
  that already contain main_entity (fuzzy match against variants). Empty residual →
  discard, reason bare_entity_restatement. Entity-absent candidates gate exactly as
  today (regression: entity-free briefs produce byte-identical Step 5 output).
- Scope: secondary safety only. Primary entity application happens post-gate at
  X.4, so the ceiling never re-evaluates enforcement-added entities — the
  entity-vs-title inflation problem does not arise for the common path.

**X.4 New: heading-form enforcement (Step 11 framing — framing.py,
validate_and_rewrite_framing)**
- Added as a framing rule, riding the stage's existing rewrite-and-re-embed path
  (re-embedding already happens here to keep cosine bands aligned).
- Every selected H2 MUST (a) contain main_entity (canonical ∪ variants), (b)
  express exactly one point. Non-conforming H2s are rewritten as entity + the
  heading's existing point and re-embedded. Warn-and-accept on residual failure,
  consistent with current framing behavior (framing_rewrites_applied /
  _accepted_with_violation).
- Point donors for any recomposition: persona-gap, PAA, Reddit, and authority-gap
  candidates (the differentiated-point sources already in the pipeline).
- Authority H2s (Step 9b) MUST inherit this rule — confirm 9b's "scope verification
  + framing" path invokes the full framing rule set, not a subset.
- H3 enforcement is out of scope for this version (flagged X.7 #3). Form
  enforcement applies to H2s only; H3s retain current behavior.

**X.5 New: advisory AIO proximity (Step 11 assembly — assembly.py)**
- When aio_target.present, compute per-selected-heading aio_proximity =
  cosine(heading, aio_answer) (same text-embedding-3-large space — no second
  embedding model in the selection/scoring path) and set-level mean + fan-out
  coverage %. Attach as a non-gating side-channel (aio_insights, available=False
  when absent), alongside reddit_insights etc.
- Proximity MUST NOT enter compute_priority (Step 7), MMR (Step 8), or any gate.
  heading_structure MUST be byte-identical with the side-channel enabled vs
  disabled.
- Active mode (proximity as a 6th priority term) is explicitly deferred — it
  opposes the information-gain weight and the restatement ceiling, requires
  threshold recalibration, and is unsupported by current evidence. Revisit only
  after a live publish-and-watch test (X.6).

**X.6 Measurement loop (required before any active mode)**
- Persist, per published article, whether it appears in the AIO and earns the
  citation link-back (aio_target.cited_sources already captured) against GSC
  position. This is the only thing that can validate proximity/form reward on our
  own sites and is the graduation criterion for reconsidering X.5 active mode.

**X.7 Flagged for sign-off**
- Research-enrichment propagation (blocking). The Writer prefers Research's enriched
  heading_structure over the brief's. Entity form enforced in the brief is void if
  Research re-touches headings without preserving it. Decision required: propagate
  main_entity + the form rule into Research's enrichment, or re-assert form at the
  Writer. Trace Research's heading handling before merge. Confirm.
- AIO target TTL. aio_target rides the 7-day (keyword, location_code) brief cache;
  real AIO volatility is higher. Accept shared TTL, or set a shorter AIO-only
  refresh. Confirm.
- H3 form enforcement deferred — H2-only this version. Confirm.
- 3-large only in the AIO path (no Gemini track) — required for score validity
  against existing gates. Confirm.
- Entity derivation deterministic (no LLM) in the default path — feeds a hard rule,
  so reproducibility is prioritized; multi_entity_flag is the hook for optional
  later LLM adjudication. Confirm.

**X.8 Metadata additions (BriefMetadata)**
Echo for tuning/audit: main_entity_source, main_entity_confidence,
multi_entity_flag, headings_entity_enforced_count, headings_form_violation_count,
bare_entity_restatement_count, aio_present, aio_proximity_mean,
aio_fanout_coverage_pct, plus the new thresholds (entity_match_fuzz_ratio,
entity_keyword_sanity_floor).

**X.9 Acceptance**
- AIO-present keyword: aio_target.present=true; main_entity.source="aio"; every H2
  carries the entity and one point; aio_insights populated with per-heading
  proximity + coverage.
- AIO-absent keyword: main_entity.source="title_fallback"; H2s still
  entity-enforced against the title entity; aio_insights.available=false; no abort.
- Bare-entity candidate discards with bare_entity_restatement; a residual that
  restates the title discards at the ceiling as before.
- Entity-free regression: a brief run with enforcement disabled is byte-identical
  to v2.6 output; side-channel toggle leaves heading_structure unchanged.
- Schema 2.7 hydrates; EXPECTED_MODULE_VERSIONS["brief"] matches; extra='forbid'
  holds.
- Authority H2s (9b) are entity-enforced.

**Evidence level.** Heading form (entity + one point): high — validated as part of
the study's best combination, implemented as a hard rule. Heading proximity: low —
advisory only, pending the X.6 loop. Specific study figures are directional
(single-operator study, noted scraper limits); none are encoded as thresholds.

**Out of scope (cross-ref).** Sentence-level extractable-snippet enforcement (lead
each H2 with an entity-naming, query-answering, self-contained sentence) belongs
Writer-side as a new format_directive enforced by a validator sibling to the
Writer's Step 6.7 — it follows the existing min_h2_body_words precedent and is
specced separately.
