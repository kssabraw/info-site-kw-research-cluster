# Decisions Log

Architecture Decision Records (ADRs) — narrowly-scoped, dated
implementation decisions. Each ADR documents one concrete choice with
its rationale and consequences.

## Which file does a decision go in?

There are two decision docs in this project. The split is:

| It belongs here (`decisions-log.md`) | It belongs in [`decisions-and-reasoning.md`](decisions-and-reasoning.md) |
|---|---|
| One specific technical choice | A class of decisions or a principle |
| Has a date and a status | Timeless / topic-organized |
| Could plausibly be reversed in a future ADR | Reversing it would mean rethinking the project |
| Example: "use HALFVEC(3072), not VECTOR(3072)" | Example: "use OpenAI embeddings, not Voyage" |

If you're not sure, default to **here** (ADR). Granular is fine; the
log is append-only and never deleted. The other doc is for thematic
reasoning — if a topic doesn't have a top-level section there already,
your decision probably isn't strategic enough to need one.

When an ADR captures the implementation of a strategic choice already
discussed in `decisions-and-reasoning.md`, link back to that section
rather than duplicating the reasoning.

## ADR format

```
## ADR-NNN: <Short title>

- **Date:** YYYY-MM-DD
- **Status:** Proposed | Accepted | Deprecated | Superseded by ADR-MMM
- **Context:** What problem are we solving? What constraints exist?
- **Decision:** What was decided? (one sentence)
- **Consequences:** What follows? Both positive and negative.
- **Alternatives considered:** What else was evaluated and why rejected?
- **Related:** Optional cross-refs to other ADRs, docs, or code.
```

ADRs are numbered sequentially. Don't renumber. If superseded, mark
status and link to the new ADR rather than editing the old one.

---

## ADR-001: Use DataForSEO API exclusively for keyword discovery

- **Date:** 2026-05-17
- **Status:** Accepted
- **Context:** Need to discover ~10–15K keywords per niche. Industry
  default is Semrush at ~$140/month + manual CSV exports.
- **Decision:** Use DataForSEO API only. No Semrush.
- **Consequences:**
  - Programmatic end-to-end; no manual CSV step in any phase.
  - Cost drops from $140/month to ~$15-20 per site run.
  - Lose ~5-10% coverage of obscure long-tails.
  - Lose Semrush UI for data browsing (not needed since pipeline is
    headless).
- **Alternatives considered:** Semrush (manual workflow), hybrid
  (Semrush seeds → DataForSEO expansion), Ahrefs API. All rejected for
  reasons documented in the linked strategic discussion.
- **Related:** Full reasoning in [decisions-and-reasoning.md →
  Decision: DataForSEO only, not Semrush](decisions-and-reasoning.md#decision-dataforseo-only-not-semrush).

---

## ADR-002: Use OpenAI text-embedding-3-large for clustering embeddings

- **Date:** 2026-05-17
- **Status:** Accepted
- **Context:** Need an embedding model for HDBSCAN clustering of
  ~12-15K keywords per site. Options span Voyage 3 Large (best
  benchmarks), OpenAI 3-large (widely supported), Cohere Embed v4,
  BGE-M3 (self-hosted).
- **Decision:** OpenAI `text-embedding-3-large`, default 3072 dims with
  Matryoshka reduction available.
- **Consequences:**
  - One vendor surface (already using OpenAI elsewhere in pipeline).
  - Cost is negligible at our scale (~$0.10 per site run).
  - ~5% quality gap to Voyage on clustering benchmarks, accepted.
  - Matryoshka reduction to 1024 or 1536 available if storage becomes
    a constraint (it isn't at current scale).
- **Alternatives considered:** Voyage 3 Large (better but new SDK),
  BGE-M3 self-hosted (free but engineering overhead), older
  sentence-transformers (10-pt MTEB gap, outdated training data).
- **Related:** Full reasoning in [decisions-and-reasoning.md →
  Decision: OpenAI text-embedding-3-large, not Voyage or self-hosted](decisions-and-reasoning.md#decision-openai-text-embedding-3-large-not-voyage-or-self-hosted).

---

## ADR-003: Store embeddings as HALFVEC(3072), not VECTOR(3072)

- **Date:** 2026-05-17
- **Status:** Accepted
- **Context:** `text-embedding-3-large` is 3072-dim native (see
  ADR-002). pgvector's HNSW index has a hard 2000-dim ceiling on the
  `VECTOR` type. The original schema declared `VECTOR(3072)` plus a
  HNSW index, which fails at deploy with `column cannot have more than
  2000 dimensions for hnsw index` — and the failure was silent under
  psql's default `ON_ERROR_STOP=off`.
- **Decision:** Change `keyword_embeddings.embedding` to `HALFVEC(3072)`
  with a `halfvec_cosine_ops` HNSW index. pgvector's HNSW supports
  `HALFVEC` up to 4000 dims. Also enforce `ON_ERROR_STOP=1` in schema
  deployment so future partial-deploy failures surface.
- **Consequences:**
  - HNSW index now builds successfully on Supabase (pgvector 0.8.x).
  - Storage halves: ~6 KB per row (was ~12 KB), ~90 MB per site
    (was ~180 MB).
  - Half-precision arithmetic introduces sub-1% cosine error at 3072
    dims, well below the noise floor of HDBSCAN clustering on
    semantic-similarity vectors.
  - Adds a soft dependency on pgvector ≥ 0.7.0 (Supabase ships 0.8.x).
- **Alternatives considered:**
  - Reduce dimensions via Matryoshka to 1024 or 1536 (rejected: changes
    the dimensional commitment already made in three docs, and storage
    was not the constraint).
  - Use IVFFlat instead of HNSW (rejected: same 2000-dim ceiling).
- **Related:** ADR-002, `schema/migrations/0001_initial_schema.sql`,
  [database-schema.md → keyword_embeddings](database-schema.md#keyword_embeddings).

---

## ADR-004: Define `clusters.confidence_score` as a weighted sum of three signals

- **Date:** 2026-05-17
- **Status:** Accepted
- **Context:** `clusters.confidence_score` (NUMERIC(3,2), range 0–1) drives
  `confidence_auto_approve_threshold` in site YAML — clusters above the
  threshold skip human review. The schema reserved the field but no
  formula was specified, leaving the auto-approval decision implementation-
  defined. For YMYL niches like retatrutide this is a real risk: a cluster
  could skip review based on whatever number Phase 10 happens to produce.
- **Decision:** Define `confidence_score` as the weighted sum:

  ```
  confidence_score =
      0.50 * intra_similarity      # how tight the cluster is
    + 0.30 * intent_agreement      # how confident intent classification was
    + 0.20 * serp_overlap          # whether members share SERP territory
  ```

  Where each component is normalized to [0, 1]:

  - `intra_similarity` = mean pairwise cosine similarity of member
    embeddings, clipped to [0, 1]. (Cosine on normalized embeddings is
    in [-1, 1]; we clip negatives to 0 since negative similarity inside
    a cluster signals a clustering failure, not a low confidence.)
  - `intent_agreement` = mean of `raw_keywords.intent_confidence` across
    cluster members. Already in [0, 1].
  - `serp_overlap` = mean pairwise Jaccard of the top-10 SERP URL sets
    across cluster members.

  Fallback: if no SERPs are available for cluster members (e.g.,
  Phase 02 was skipped or this cluster's keywords are below the SERP
  fetch volume cutoff), drop the serp_overlap term and renormalize to:

  ```
  confidence_score =
      0.625 * intra_similarity
    + 0.375 * intent_agreement
  ```

  Single-member clusters get `confidence_score = NULL` (not a synthetic
  high value) and are always routed to human review regardless of the
  auto-approve threshold.
- **Consequences:**
  - Auto-approval is now defined by a single formula across all phase
    implementations and re-runs — `pipeline_jobs.config_snapshot` plus
    the formula in this ADR is sufficient to reproduce the score.
  - The 0.50/0.30/0.20 weights are a starting point. Tuning them is a
    parameter change and should be a new ADR (don't edit this one).
  - NULL confidence on single-member clusters means the auto-approve
    threshold cannot accidentally approve a cluster of one keyword.
- **Alternatives considered:**
  - Use intra_similarity alone (simplest, but ignores intent agreement
    which catches misclassified-keyword pollution).
  - Use a learned model (premature — no training data and no labels).
  - Multiplicative combination of the three signals (rejected: a single
    weak signal would dominate; additive with explicit weights is
    easier to reason about and tune).
- **Related:** [pipeline-phases.md → Phase 10](pipeline-phases.md#phase-10-hdbscan-clustering),
  [database-schema.md → clusters](database-schema.md#clusters).

---

## ADR-005: Promote keywords in thin intent buckets to single-member clusters, do not run HDBSCAN

- **Date:** 2026-05-17
- **Status:** Accepted
- **Context:** Phase 10 clusters within each intent bucket separately
  (per the per-intent-clustering decision in
  [decisions-and-reasoning.md → Intent classification before clustering](decisions-and-reasoning.md#decision-intent-classification-before-clustering)).
  Keyword distributions across intents are heavily skewed in practice:
  EDUCATIONAL/SAFETY/COMPARISON typically have hundreds of keywords;
  rare-but-important intents like VENDOR/LEGAL/ACCESS may have 10–30.
  With `min_cluster_size = 5`, HDBSCAN tends to dump the entire thin
  bucket into the noise label (-1), which would discard the keywords
  that most need human attention — exactly the regulatory-sensitive
  ones listed in `require_human_review_intents`.
- **Decision:** When an intent bucket has fewer than
  `thin_bucket_threshold` keywords (default 50), skip HDBSCAN for that
  bucket. Promote every keyword to its own single-member cluster with
  `confidence_score = NULL`. Per ADR-004, NULL confidence routes to
  human review regardless of the auto-approve threshold.
- **Consequences:**
  - Rare-intent keywords are never lost to clustering noise.
  - Review burden for thin intents is bounded by keyword count, not
    arbitrary clustering outcomes — reviewers know exactly what they're
    seeing.
  - Single-member clusters for thin-intent keywords mix with
    single-member noise clusters from dense intents in the review
    queue. Reviewers should be able to distinguish them via
    `cluster_members.count = 1` plus the intent — no schema change
    needed.
  - The 50-keyword threshold is a parameter, not a constant — sites
    that need different sensitivity can override in YAML.
- **Alternatives considered:**
  - Lower `min_cluster_size` for thin buckets to 2 or 3 (rejected: at
    those sizes HDBSCAN's density model breaks down and produces
    arbitrary groupings).
  - Merge thin buckets into a single "miscellaneous" bucket for
    clustering, then re-tag (rejected: defeats the whole reason for
    per-intent clustering — mixed intents in one bucket).
  - Keep the keywords but tag them as `cluster_id = NULL` rather than
    creating single-member clusters (rejected: breaks the
    cluster-is-the-review-unit invariant in Phase 12).
- **Related:** ADR-004, [pipeline-phases.md → Phase 10](pipeline-phases.md#phase-10-hdbscan-clustering),
  [decisions-and-reasoning.md → Intent classification before clustering](decisions-and-reasoning.md#decision-intent-classification-before-clustering).

---

## ADR-006: Keyword normalization rules

- **Date:** 2026-05-17
- **Status:** Accepted
- **Context:** `raw_keywords.keyword_normalized` is the dedup key
  (`UNIQUE (site_id, keyword_normalized)`) and the join key for most
  downstream phases. The original design note said "lowercase + stripped
  + collapsed whitespace" and stopped there — no rule for hyphens,
  plurals, possessives, Unicode, parentheticals, brand capitalization
  (`LY3437943` vs `ly3437943`), or punctuation. Without a pinned spec,
  different phases will normalize differently, the UNIQUE constraint
  will fire on apparent-duplicates from different writers, and dedup
  will silently miss near-duplicates.
- **Decision:** Normalization is the composition of these steps,
  applied in order. The canonical implementation lives in
  `pipeline/utils/normalize.py::normalize_keyword(s: str) -> str`.
  Every writer to `raw_keywords.keyword_normalized` and
  `discovered_keywords.keyword` (for dedup comparison) must call this
  function and no other.

  1. **Unicode normalize** to NFKC. Composes accents, normalizes width.
  2. **Casefold** (not lowercase). `str.casefold()` handles non-ASCII
     case more reliably than `.lower()` (e.g., German `ß` → `ss`).
  3. **Replace** these characters with a single space: `( ) [ ] { } / \ | _ , ; : ! ? " ' ` (backtick) `~ * + = < > & % $ # @`
     Note: the apostrophe `'` is included, so `retatrutide's` →
     `retatrutide s`. After whitespace collapse and trailing-token
     dropping (step 6), it becomes `retatrutide`.
  4. **Preserve** ASCII letters, digits, hyphens, periods, and spaces.
     Hyphens inside words are preserved (`retatrutide-info`); periods
     in decimals and abbreviations are preserved (`2.5 mg`, `u.s.`).
  5. **Trim** leading/trailing whitespace; **collapse** runs of internal
     whitespace to single spaces.
  6. **Drop trailing single-letter tokens** of length 1 — catches the
     post-apostrophe-strip artifacts (`retatrutide s` → `retatrutide`)
     and stray standalone letters from punctuation removal. Tokens of
     length ≥ 2 are preserved (`mg`, `iv` stay).
  7. **Reject** the result if empty after trimming — caller raises;
     never write an empty `keyword_normalized`.

  **What this deliberately does NOT do:**
  - **Stemming.** `retatrutides` and `retatrutide` are different
    keywords; SERPs often differ. Embedding similarity handles
    semantic merging at clustering time.
  - **Hyphen removal.** `retatrutide-info` stays as a single normalized
    string (with the hyphen), distinct from `retatrutide info`.
  - **Number-to-word or word-to-number.** `2.5 mg` and `two point five
    mg` stay distinct.
  - **Diacritic stripping.** NFKC composes but does not strip — `café`
    stays `café`, not `cafe`. (Diacritics inside ASCII-dominant
    keywords are vanishingly rare in current niches; revisit if a
    multi-language site is launched.)

  **Belt and suspenders:** the schema adds a CHECK constraint on
  `raw_keywords.keyword_normalized` that catches the cheapest
  violations (uppercase letters, leading/trailing whitespace, double
  spaces, empty string). This does NOT replace the canonical
  normalizer — it only catches accidental bypasses.

- **Consequences:**
  - One canonical normalizer; all dedup is deterministic and stable
    across re-runs.
  - The CHECK constraint surfaces direct-INSERT bugs (e.g., a
    debugging script that bypasses `pipeline/utils/database.py`)
    before they corrupt dedup state.
  - Hyphenated compounds (`retatrutide-info`, `glp-1`) get treated as
    single tokens — embedding clustering will still group them with
    their non-hyphenated variants if semantically close, so the cost
    is small.
  - Possessives ('s) collapse to the base via the apostrophe + trailing-
    single-letter rules. This is opinionated; if it causes problems
    revisit with a new ADR.

- **Alternatives considered:**
  - Use the database as the normalizer (GENERATED column for
    `keyword_normalized`). Rejected: Unicode NFKC and `casefold` are
    not available in plain Postgres without extensions; pushing to a
    Python normalizer keeps the rules portable.
  - Aggressive normalization (strip hyphens, strip diacritics,
    Porter stemming). Rejected: erases SERP-relevant distinctions that
    DataForSEO returns as separate keywords with different volumes.
  - Per-phase normalizers tuned to each phase's needs. Rejected: this
    is the exact failure mode we're fixing.

- **Related:** `pipeline/utils/normalize.py` (to be written),
  [database-schema.md → raw_keywords](database-schema.md#raw_keywords).

---

## How This Document Is Maintained

Add a new ADR when:

- A non-obvious technical choice is made (parameter tuned, library
  picked, tradeoff resolved)
- An implementation pattern is established that future code should
  follow
- The implementation of a strategic decision happens (link back to
  `decisions-and-reasoning.md`)

Don't add ADRs for:

- Obvious technical choices ("use UTF-8 encoding")
- Strategic principles or scoping (those belong in
  `decisions-and-reasoning.md`)
- Per-phase mechanics (those belong in `pipeline-phases.md`)

ADRs are numbered sequentially. Don't renumber when adding new ones.
If an ADR is superseded, mark its status (`Superseded by ADR-MMM`) and
link to the new ADR. Do not edit the body of a superseded ADR — history
is the point.
