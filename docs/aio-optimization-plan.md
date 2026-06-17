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

## 1. What this is

An **AI-Overview eligibility layer**. Both existing content modules (SIE, Brief
Gen) are tuned for *organic SERP* competitiveness (term modeling, coverage,
information gain). None of them try to get the page's text **lifted into Google's
AI Overview**. This research adds that: capture the live AIO answer, derive the
single main entity it repeats, and construct/enforce headings that sit close to
that answer in embedding space.

Two evidence levels, kept strictly separate (the research's own framing, which we
adopt):
- **Heading FORM** (entity + exactly one answer-derived point per heading) —
  **high confidence → hard rule.**
- **AIO-answer PROXIMITY** (cosine scoring, MCS climbing) — **low confidence →
  advisory, non-gating, deferred behind a measurement loop.**

---

## 2. Gap analysis — what's already in the plans vs. missing

| Research element | Lands on | Status | Note |
|---|---|---|---|
| §4.X Decision-Fit Mapping | Brief Gen (trigger/gating) + Writer (render) | ❌ Missing | Co-owned — see §3. |
| §4.X Max Cosine Synthesis (candidate-pool + greedy/beam cosine climb) | Brief Gen | ❌ Missing | The low-confidence, most ambitious piece. Defer. |
| X.1 AIO target capture (answer_text, cited_sources, fanout) | Brief Gen Step 1 | ❌ Missing | Plan's SERP scrape gets headings/titles/metas + feature flags, **not** the AIO block. Research claims it rides the existing depth-20 DataForSEO call — **verify DataForSEO returns the AIO block.** |
| §13.X.8 / X.2 Main-entity derivation (`entity.py`, new Step 3.6) | Brief Gen | ❌ Missing as a feature; ✅ deps already present | **spaCy `en_core_web_sm` already locked** (SIE §9, shared dep). **3-large already in Brief Gen** for the tie-break/sanity embeddings. Building blocks exist; module doesn't. Deterministic, no LLM in default path → free + testable. |
| X.3 Residual restatement gate (apply 0.78 ceiling to entity-stripped residual) | Brief Gen Step 5 (`graph.py`) | ⚠️ Partial | The **0.55 floor / 0.78 ceiling already exist**. This is a refinement (strip entity first), not a new gate. |
| X.4 Heading-form enforcement (entity + one point, every H2) | Brief Gen Step 11 framing (`assemble.py`) | ⚠️ Partial | The **framing validator + title-case stage already exists**. New rule rides its existing rewrite-and-re-embed path. The high-confidence core. |
| X.5 Advisory AIO proximity side-channel | Brief Gen assembly | ❌ Missing | Net-new, explicitly non-gating. Defer. |
| X.6 Measurement loop (post-publish AIO citation + GSC) | Beyond M13 — needs publish telemetry | ❌ Missing entirely | Graduation criterion before any "active" proximity mode. We have no published-article telemetry anywhere yet. |
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

---

## 4. Open conflicts to resolve before this slots in

1. **Gemini vs OpenAI embeddings — research self-contradicts; we rolled Gemini
   back.** MCS (§4.X) says "MUST be Gemini (Vertex)"; the drop-in PRD §X.5/X.7
   walks it back to "3-large only, no Gemini track." **We rolled Gemini back
   2026-06-16** (poor relevance discrimination) and are locked on OpenAI
   `text-embedding-3-small` app-wide / `3-large` inside Brief Gen. → **Adopt the
   3-large advisory framing; drop the "MUST be Gemini" line.** Caveat the research
   itself raises: 3-large is a *proxy* for the model judging AIO, which is exactly
   why proximity stays advisory/non-gating.
2. **Version + module-name mismatch.** Research is written against **prod v2.6 →
   2.7** with prod filenames (`dataforseo.py`, `parsers.py`, `entity.py`,
   `graph.py`, `framing.py`, `assembly.py`). Our M13 plan targets **v2.3** with a
   different layout (`sources.py`, `intent.py`, `graph.py`, `select.py`,
   `authority.py`, `faq.py`, `assemble.py`). Per `blog-writer-live-contract.md`,
   **prod v2.6 wins over PRD v2.3.** → Adopting this likely means **rebasing M13
   onto v2.6 first**, then layering 2.7. Bigger than a feature add.
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

**Headline:** nothing collides **if you take the curated PRD §X path** — §X was
engineered to slot in beside the existing selection machinery (additive capture,
post-gate form enforcement, non-gating proximity). Collisions are real only when
(A) the implementation order is wrong, (B) the raw §4.X MCS is taken literally as
a selection driver, or (C) the Gemini embedding requirement is honored.

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

### B. The one you must consciously REJECT: MCS-as-selection + Gemini

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

→ PRD §X already neutralizes both: keeps organic selection **intact**, demotes
proximity to a **non-gating side-channel**, mandates **"3-large only, no Gemini
track."** **Adopt §X's framing, not §4.X's literal one.**

### C. Controlled collisions (designed regression-safe)

- **X.3 modifies Step 5** (existing gate) but is byte-identical for entity-absent
  candidates ("entity-free briefs produce byte-identical Step 5 output").
- **X.4 rides the existing Step 11 framing rewrite path** (composes, doesn't
  replace). **Open gap it flags itself:** does **authority-H2 generation (Step
  9b)** invoke the *full* framing rule set or a subset? If a subset, authority H2s
  **bypass entity enforcement** — a real hole to verify (→ §6).
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

## 5. Proposed slicing (ship-now vs deferred)

**Ship-now (high-confidence, deterministic, rides existing seams):**
- X.1 AIO target capture (Brief Gen Step 1) — pending the "does DataForSEO return
  the AIO block?" verification.
- X.2 / §13.X.8 Main-entity derivation (new Step 3.6, `entity.py`) — deterministic,
  free, fully fixture-testable.
- X.3 Residual restatement gate refinement (Step 5).
- X.4 Heading-form enforcement (Step 11 framing) — the core hard rule.
- Decision-fit **detection + `format_directive`** (Brief Gen side only).
- X.8 metadata fields + schema bump (gated on the v2.6 rebase decision, §4 #2).

**Deferred (low-confidence / advisory / needs telemetry):**
- §4.X MCS candidate-pool generation + greedy/beam cosine climbing.
- X.5 advisory AIO proximity side-channel.
- X.6 measurement loop (and any future "active" proximity mode).
- Decision-fit **rendering + validator** (Writer / M14).
- Writer-side extractable-snippet directive (separate spec, M14).

---

## 6. Next actions (not yet done)

- [ ] Owner sign-off on the §4 conflicts (esp. the v2.6 rebase).
- [ ] Verify DataForSEO surfaces the AIO block on the depth-20 SERP call.
- [ ] Confirm the Writer never re-derives headings (X.7 propagation N/A check).
- [ ] **Verify Step 9b (authority-H2 generation) invokes the FULL Step-11 framing
      rule set, not a subset** — otherwise authority H2s bypass entity enforcement
      (collision §4.5-C). Trace the 9b "scope verification + framing" path before
      building X.4.
- [ ] **Enforce the X.3→X.4 implementation ordering** (derive 3.6 → residual gate
      5 → form enforce 11) so entity tokens never reach MMR/the restatement ceiling
      (collision §4.5-A). Add a regression test: entity-free brief = byte-identical
      Step 5 + Step 11 output.
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
