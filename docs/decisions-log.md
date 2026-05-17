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

## ADR-007: `is_included` is the sole exclusion signal; drop 'excluded' from `tier` enum

- **Date:** 2026-05-17
- **Status:** Accepted
- **Context:** `raw_keywords` had two columns that could express
  exclusion: `tier IN ('primary','secondary','longtail','branded','excluded')`
  and `is_included BOOLEAN`. Nothing constrained them to agree —
  empirically verified, `tier='excluded' AND is_included=TRUE` was
  accepted by the schema. Two writers, two semantics, guaranteed
  drift. Worse: downstream phases that filter on `is_included` would
  silently include `excluded`-tier rows that some other phase had
  already marked as excluded.
- **Decision:** `is_included` is the single source of truth for
  whether a keyword participates in downstream phases. `'excluded'`
  is removed from the `tier` enum. `tier` now means "what *role*
  does this keyword play in the topic taxonomy" (primary | secondary
  | longtail | branded) — orthogonal to inclusion.

  Phase 06 (relevance filtering) sets `is_included = FALSE` and
  `exclusion_reason` for filtered-out keywords; it does not touch
  `tier`.

- **Consequences:**
  - One signal for "is this keyword live?" — `is_included`.
  - `tier` becomes a positive classification only; no more "is this
    a role or a status?" confusion.
  - Any existing-but-shouldn't-exist `tier='excluded'` rows would
    fail to migrate. Pre-launch, nothing is deployed; no migration
    needed beyond editing both schema files in place.
- **Alternatives considered:**
  - Add a CHECK enforcing `(tier = 'excluded') = (is_included = FALSE)`.
    Rejected: redundant column with a tautological constraint is worse
    than dropping the column value entirely.
  - Drop `is_included` and use `tier = 'excluded'`. Rejected: boolean
    is simpler and cheaper to filter on; the `exclusion_reason` TEXT
    column already exists alongside `is_included` as a coherent pair.
- **Related:** [database-schema.md → raw_keywords](database-schema.md#raw_keywords).

---

## ADR-008: Enforce `topics.subfolder` and `topics.slug` formats via CHECK; drop redundant UNIQUE

- **Date:** 2026-05-17
- **Status:** Accepted
- **Context:** `topics.url_path` is a STORED GENERATED column:
  `subfolder || slug || '/'`. Nothing validated the inputs.
  Empirically verified that the schema accepted:
  - `subfolder='/guides'` (no trailing slash) + `slug='how-to'` →
    `url_path = '/guideshow-to/'`
  - `subfolder=''` + `slug='kw'` → `url_path = 'kw/'`
  - `subfolder='/guides/'` + `slug=''` → `url_path = '/guides//'`

  Each is a malformed URL that downstream article generation would
  consume blindly. Additionally, the table had both
  `UNIQUE (site_id, url_path)` and `UNIQUE (site_id, slug, subfolder)`,
  which constrain the same set of values (url_path is derived from the
  inputs). One was a redundant index paying write cost for no
  benefit.

- **Decision:**

  1. Add CHECK constraints on the inputs:
     - `subfolder ~ '^/([a-z0-9-]+/)+$'` — must start and end with `/`,
       segments are kebab-case lowercase alphanumerics with hyphens.
       Examples that pass: `/get/cost/`, `/guides/`. Fail:
       `/guides`, `guides/`, `/Get/Cost/`, `//`, `/get_cost/`.
     - `slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'` — kebab-case, no leading
       or trailing hyphen, never empty. Examples that pass:
       `retatrutide-side-effects`, `dose-2-5mg`. Fail: empty,
       `-foo`, `foo-`, `Foo-Bar`, `foo--bar`.

  2. Drop `UNIQUE (site_id, slug, subfolder)` — it is functionally
     identical to `UNIQUE (site_id, url_path)`.

- **Consequences:**
  - Malformed URL paths are rejected at insert time, surfacing
    convention bugs in whichever phase wrote them.
  - One fewer composite index on `topics`, saving write throughput
    and storage.
  - Sites whose folder taxonomies don't fit kebab-case (e.g., a niche
    that wants underscores or non-ASCII paths) need a new ADR to
    relax these regexes. Acceptable: SEO-conventional URL paths
    are kebab-case lowercase by default.
- **Alternatives considered:**
  - Normalize subfolder/slug at write time instead of checking.
    Rejected: the CHECK approach surfaces bugs at the source rather
    than silently fixing up bad inputs.
  - Make `url_path` the only constrained column with a CHECK on its
    final shape. Rejected: input checks give better error messages
    ("subfolder missing trailing slash") than output checks ("url_path
    fails regex").
- **Related:** [database-schema.md → topics](database-schema.md#topics).

---

## ADR-009: Replace `topics.depends_on_topic_ids` array with `topic_dependencies` junction table

- **Date:** 2026-05-17
- **Status:** Accepted
- **Context:** `topics.depends_on_topic_ids BIGINT[]` had no
  referential integrity — Postgres cannot enforce per-element FK
  constraints on array elements. Empirically verified: inserting
  `depends_on_topic_ids = ARRAY[99999, 88888]` (nonexistent IDs)
  succeeds. The downstream article generator, which reads these to
  order article creation by dependency, would hit dangling references
  and either crash or silently skip.
- **Decision:** Drop the array column. Add a junction table
  `topic_dependencies` with proper FKs:

  ```sql
  CREATE TABLE topic_dependencies (
      topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
      depends_on_topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE RESTRICT,
      site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      PRIMARY KEY (topic_id, depends_on_topic_id),
      CHECK (topic_id != depends_on_topic_id)
  );
  ```

  `ON DELETE RESTRICT` on `depends_on_topic_id` is intentional: you
  cannot delete a topic that other topics depend on. The dependent
  topics must either drop their dependency first or be deleted first.
  This is the right default for a topic graph; explicit is better than
  the silent dangling-reference behavior the array had.

  The self-reference CHECK prevents `A depends on A`.

- **Consequences:**
  - Article generation can `JOIN topic_dependencies` and trust the
    references resolve. No defensive checks needed downstream.
  - Insertion is two-step for topics with deps: insert the topic,
    then insert the dependency rows. Standard junction pattern.
  - Deletion semantics are now safer (RESTRICT surfaces broken
    references) but require explicit cleanup. Pre-launch this is
    free; no production data depends on the old shape.
  - The `topic_dependencies.site_id` denormalization shares the same
    consistency caveat as other denormalized site_id columns (see the
    Multi-Tenancy OPEN section in architecture.md). Out of scope for
    this ADR.
- **Alternatives considered:**
  - Keep the array, add a trigger that validates references on
    INSERT/UPDATE. Rejected: triggers are easy to miss and add
    invisible behavior; junction tables are the standard pattern.
  - Add an arbitrary `relationship_type` column to handle multiple
    kinds of dependencies. Rejected: `topic_relationships` already
    exists for that purpose; `topic_dependencies` is specifically the
    ordering edge.
- **Related:** [database-schema.md → topics](database-schema.md#topics),
  [database-schema.md → topic_relationships](database-schema.md#topic_relationships).

---

## ADR-010: YAML configs are immutable; runtime-mutable state lives in `sites.runtime_state`

- **Date:** 2026-05-17
- **Status:** Accepted
- **Context:** Site YAML configs were intended to be immutable inputs
  snapshotted into `pipeline_jobs.config_snapshot` for reproducibility.
  But the YAML schema included `review.google_sheets.sheet_id: null
  # Set after first export` — explicitly a mutable field. Phase 12
  would write back to YAML after creating a sheet. This had three
  problems:

  1. "Reproducibility from `config_snapshot`" was only partial — the
     snapshot was a point-in-time copy of a moving target.
  2. YAML mutations create noisy git diffs (`sheet_id: "abc..."` lands
     in commits) that conflate operational state with intentional
     config changes.
  3. Future operational state (cache invalidation timestamps, run
     counters, derived metadata) would have nowhere to live without
     reopening this question every time.

- **Decision:** YAML configs are immutable inputs. Anything that needs
  to persist across runs as derived/operational state lives in
  `sites.runtime_state JSONB DEFAULT '{}'`. Phase modules read and
  write this column directly through `pipeline/utils/database.py`.

  Concrete change: `review.google_sheets.sheet_id` is removed from the
  site YAML. Phase 12 stores the sheet ID at
  `sites.runtime_state -> 'phase_12' -> 'google_sheets_sheet_id'`.

  `pipeline_jobs.config_snapshot` continues to capture the YAML at run
  time, but the contract is now:
  *"Given the same YAML snapshot AND the same `sites.runtime_state`,
   the pipeline produces the same outputs."* The snapshot is
  necessary but no longer sufficient on its own.

- **Consequences:**
  - YAML diffs in git are now purely intentional configuration
    changes. No more "Phase 12 wrote a sheet ID, here's a commit you
    didn't ask for."
  - `runtime_state` is a small extensibility point — new phases that
    need to persist operational metadata don't require schema migrations.
  - `pipeline_jobs.output_summary` should capture relevant
    `runtime_state` snapshots when needed for full reproducibility
    (e.g., snapshot the sheet ID into output_summary at Phase 12
    export time).
  - Document the JSONB structure conventions in
    `docs/architecture.md` Configuration System OPEN block when
    `pipeline/utils/database.py` is written.
- **Alternatives considered:**
  - Leave `sheet_id` in YAML, accept partial reproducibility.
    Rejected: this is exactly the leak we're closing.
  - Separate per-site state into a dedicated `site_state` table.
    Rejected: one column on `sites` keeps related data colocated and
    avoids a join for the common case.
  - Use `pipeline_jobs.output_summary` exclusively (sheet ID lives
    on the export job's row). Rejected: subsequent imports would
    need to look up the most recent export job's row to find the
    sheet — clumsy. Current state belongs on the entity, not on the
    history.
- **Related:** [database-schema.md → sites](database-schema.md#sites),
  [pipeline-phases.md → Phase 12](pipeline-phases.md#phase-12-review-export-and-import),
  `config/sites/retatrutide.yaml`.

---

## ADR-011: Phase 06 applies `niche_match_terms` only to direct-discovery keywords; tangential keywords pass on semantic similarity alone

- **Date:** 2026-05-17
- **Status:** Accepted
- **Context:** Phase 00 (concept mapping) uses an LLM to generate
  tangential concepts, deliberately broadening discovery beyond the
  user's `discovery.primary_seeds`. The whole point is to surface
  relevant queries like "Ozempic vs Wegovy for obesity" that don't
  contain `retatrutide` or `triple agonist` but are topically
  adjacent.

  Phase 06 (relevance filtering) was specified to apply
  `filtering.niche_match_terms` as a must-contain gate. Applied
  uniformly, this gate would filter out exactly the tangential
  keywords Phase 00 spent budget generating. The two phases were
  fighting each other.

- **Decision:** Phase 06 has two relevance paths, selected by
  `raw_keywords.tangential_distance`:

  1. **Direct-discovery path** (`tangential_distance = 0` —
     keywords sourced from primary_seeds, URL mining, or domain
     mining): apply both gates AND'd together — must contain at least
     one of `filtering.niche_match_terms` AND clear the semantic
     similarity threshold (`discovery.semantic_relevance_threshold`,
     0.65 in retatrutide).
  2. **Tangential path** (`tangential_distance >= 1` — keywords
     sourced from Phase 00 concepts or their downstream expansions):
     apply semantic similarity threshold only. The must-contain gate
     is bypassed.

  In both paths, `filtering.exclusion_terms` is applied as a hard
  reject regardless of source.

  Phase 09 (embedding generation) is a prerequisite for the semantic
  similarity component. For the direct-discovery path during initial
  filtering, an interim cosine against a niche embedding (computed
  once per site from `site_metadata.niche_description`) is sufficient
  — the full per-keyword embedding from Phase 09 isn't required.

- **Consequences:**
  - Tangential discoveries are no longer silently filtered by the
    must-contain gate; Phase 00's budget pays off.
  - The must-contain gate still protects direct-discovery from
    obviously off-niche keywords surfaced by competitor mining
    (e.g., a competitor that ranks for unrelated weight-loss queries).
  - `raw_keywords.tangential_distance` becomes load-bearing in
    Phase 06 — Phase 00 and any downstream phase that creates
    keywords from tangential sources MUST set this column correctly
    (0 for direct, 1 for first-order tangential, 2 for second-order,
    capped at 3 by the existing CHECK).
  - The interim niche embedding (one vector per site) needs a home.
    Add `sites.niche_embedding HALFVEC(3072)` in a follow-up if it
    isn't computed on-the-fly each run.

- **Alternatives considered:**
  - Apply must-contain to everything, accept the lost coverage.
    Rejected: defeats Phase 00.
  - Drop the must-contain gate entirely, rely on semantic similarity
    everywhere. Rejected: must-contain is cheap and catches obvious
    junk before the semantic step pays embedding cost. Effective
    defense in depth for direct discovery.
  - Add a separate `tangential_niche_match_terms` in config.
    Rejected: more config knobs, more drift; the
    `tangential_distance` column already carries the source signal.

- **Related:** [pipeline-phases.md → Phase 06](pipeline-phases.md#phase-06-relevance-filtering),
  [pipeline-phases.md → Phase 00](pipeline-phases.md#phase-00-concept-mapping),
  ADR-006 (normalization affects both gates).

---

## ADR-012: Enforce Critical Conventions via `scripts/check-conventions.sh` and pre-commit

- **Date:** 2026-05-17
- **Status:** Accepted
- **Context:** CLAUDE.md's "Critical Conventions" section lists rules
  (all DB access through `pipeline/utils/database.py`, all API clients
  in `pipeline/utils/`, `@track_job` decorator on every phase, no
  hardcoded niche specifics, config loading through
  `pipeline/utils/config.py`). These are rules for humans and Claude.
  No linter, no schema, no review automation. The first slip happens
  in a one-off debugging script that gets copy-pasted into the real
  pipeline; the second slip is structural drift.
- **Decision:** Add `scripts/check-conventions.sh` that grep-checks
  the conventions and exits non-zero on violation. Wire it into
  `.pre-commit-config.yaml` so it runs on every commit (and can be
  invoked directly during development or in CI).

  Covered checks today:
  - DB client imports (`psycopg2`, `psycopg`, `supabase`,
    `sqlalchemy`) only allowed in `pipeline/utils/database.py`.
  - `anthropic` only in `pipeline/utils/claude_client.py`.
  - `openai` only in `pipeline/utils/openai_client.py`.
  - `dataforseo`/`dfs` only in `pipeline/utils/dataforseo.py`.
  - `yaml.safe_load`/`yaml.load`/`yaml.full_load` only in
    `pipeline/utils/config.py`.
  - `os.environ`/`os.getenv` only in `pipeline/utils/config.py`.
  - No raw SQL string literals in `pipeline/phases/`.
  - Every `def run(` in `pipeline/phases/*.py` is preceded by
    `@track_job`.

  The script no-ops when `pipeline/` doesn't exist yet — the rules
  are locked in as declared intent before code lands, and the moment
  the first phase is added the hooks start enforcing.

  Verified: empty repo passes; synthetic violation file triggers all
  applicable checks and exits 1.

- **Consequences:**
  - Rules become testable artifacts rather than wishful prose.
  - The set of checks is the public contract; new rules require an
    ADR that adds a new check.
  - Grep-based enforcement catches obvious slips but not subtle ones
    (e.g., passing site_id from a global, dynamic SQL composition).
    Subtle enforcement is type-checker territory and waits until
    mypy/pyright is added.
  - Pre-commit is opt-in until devs install it. CI will be wired in
    when the build moves out of solo CLI development.

- **Alternatives considered:**
  - Custom Ruff rules. Rejected: more infrastructure, slower to
    iterate; grep covers the rules today.
  - Manual review checklist only. Rejected: this is what the rules
    already were; the failure mode is documented.
  - Wait until the first phase is written. Rejected: by then someone
    has already slipped.

- **Related:** `scripts/check-conventions.sh`, `.pre-commit-config.yaml`,
  CLAUDE.md → Critical Conventions.

---

## ADR-013: Enable RLS without policies; document the security posture and the trigger for adding policies

- **Date:** 2026-05-17
- **Status:** Accepted
- **Context:** Every multi-tenant table has `ENABLE ROW LEVEL
  SECURITY` but zero policies are defined. The intent is
  "service_role bypasses RLS, which is what the CLI pipeline uses;
  any other connection gets zero rows." This is the right default
  for the current single-user CLI usage, but it's a hidden
  prerequisite for any future non-service-role access (team UI,
  read-only analytics user, debugging via the Supabase anon key).
  Nothing on the roadmap currently captures that hidden prerequisite.
- **Decision:** Keep the current posture — RLS enabled, no policies,
  service_role only — and explicitly document:

  1. The posture in `schema.sql` itself as a multi-line comment
     above the `ENABLE ROW LEVEL SECURITY` block, naming the
     consequences for non-service-role connections.
  2. A placeholder `schema/policies/` directory with a README
     describing the contract a future policy set must satisfy:
     read-your-own-site, write-your-own-site, no cross-site reads
     unless a site_owners-style table is introduced.
  3. An explicit trigger condition for writing the policies, so the
     work is gated on a real event rather than indefinite deferral.

  **Trigger:** the first commit that introduces any of:
  - a `site_users` (or similar) table mapping users to sites
  - any code path that connects with a non-`service_role` key
  - the team UI (web dashboard) entry point

  must also land a policy set in `schema/policies/` and a migration
  that applies it. Reviewers should reject the first such commit if
  it doesn't.

- **Consequences:**
  - The "zero policies = empty result for non-service-role" failure
    mode is now intentional and documented, not an oversight.
  - Future work has a tracked home (`schema/policies/`) instead of
    being unaddressed.
  - The trigger is concrete and reviewable — first commit that meets
    the conditions has to do the work in the same commit.
  - No runtime change today; service_role pipeline behaves identically.
- **Alternatives considered:**
  - Disable RLS entirely until policies are designed. Rejected:
    leaves the multi-tenant tables open by default, which is the
    wrong default to forget.
  - Add a minimal "deny all" policy now. Rejected: identical to no
    policy + RLS enabled (both result in zero rows for non-service-
    role), but creates an artifact that suggests "policies are
    designed" — false signal.
  - Defer documenting this. Rejected: that's exactly how the hidden
    prerequisite stayed hidden for an entire scaffolding session.

- **Related:** `schema/policies/README.md` (placeholder),
  [database-schema.md → Row Level Security](database-schema.md#row-level-security).

---

## ADR-014: `MAX_RUN_COST_USD` is a running-total kill-switch, not a pre-flight estimate

- **Date:** 2026-05-17
- **Status:** Accepted
- **Context:** `.env.example` declares `MAX_RUN_COST_USD=100` as a
  "safety check" but no mechanism for computing the cost was
  specified. The env var was decorative — the guardrail could never
  fire because nothing tracked the running total. Two paths exist:
  (a) build pre-flight estimation per phase (hard — DataForSEO
  endpoints return variable result counts), or (b) make it a running-
  total kill-switch that aborts the moment cumulative API spend
  exceeds the cap.
- **Decision:** `MAX_RUN_COST_USD` is a **running-total kill-switch**.
  Every API client (DataForSEO, OpenAI, Anthropic) reports the
  estimated cost of each call to a shared `CostTracker` that lives
  in the pipeline run context. Before any API call the client checks
  `tracker.would_exceed(estimated_cost)`; if so it raises
  `CostBudgetExceeded`. The phase catches this, marks the
  `pipeline_jobs` row as `failed`, and exits.

  **Contract for each API client utility:**

  - Has a constant per-call cost table (e.g.,
    `OpenAIClient.COST_PER_1K_EMBEDDING_TOKENS = 0.00013`).
  - Every public method computes the call's cost before issuing it.
  - Every public method calls `cost_tracker.charge(method_name, cost)`
    after a successful response (and `charge_failed` on failure if
    the API charges for failed calls).
  - Every public method first calls `cost_tracker.check(estimated_cost)`
    which raises `CostBudgetExceeded` if it would put the run over.

  **Contract for `CostTracker`:**

  - One instance per pipeline run, threaded through phase context.
  - Loaded with `MAX_RUN_COST_USD` from env at run start (default 100).
  - Exposes `total`, `by_phase`, `by_endpoint` for reporting.
  - On every charge, write the latest totals to the in-progress
    `pipeline_jobs.output_summary` so a killed run still has the
    cost breakdown.
  - On `CostBudgetExceeded`, the message includes total spend, the
    method that tripped the cap, and the env var name (so the
    operator can decide whether to raise the cap or abort).

  **What this is NOT:**

  - Not a pre-flight estimate. We don't know in advance how many
    keywords a DataForSEO `keyword_ideas` call will return.
  - Not a per-phase cap (could be added later as `MAX_PHASE_COST_USD_*`
    env vars if needed).
  - Not retry-aware. A failed call that still costs money charges
    once; a successful retry charges again. Both are reported.

  **Cost table seed values** (to be refined with real billing data;
  add a new ADR when tuning):

  | Endpoint | Approx. cost |
  |---|---|
  | OpenAI `text-embedding-3-large`, per 1K tokens | $0.00013 |
  | Anthropic Haiku 4.5, per 1K input tokens | ~$0.001 |
  | Anthropic Haiku 4.5, per 1K output tokens | ~$0.005 |
  | DataForSEO `keyword_ideas`, per request | ~$0.05 |
  | DataForSEO `serp/google/organic`, per request | ~$0.0025 |
  | DataForSEO `ranked_keywords`, per request | ~$0.01 |
  | DataForSEO `keywords_for_site`, per request | ~$0.05 |
  | DataForSEO `keyword_overview`, per 1K keywords | ~$0.075 |

- **Consequences:**
  - `MAX_RUN_COST_USD` becomes a real safety net rather than a
    placeholder.
  - The CostTracker is a small but real component every API client
    depends on — adds coupling, but the alternative is unbounded
    spend on a runaway phase.
  - Killed runs preserve their partial cost breakdown in
    `pipeline_jobs.output_summary`, which doubles as audit data
    for tuning the cap.
  - The cost table is a moving target. When DataForSEO or vendor
    pricing changes, tune the constants and add a new ADR (don't
    edit this one).
- **Alternatives considered:**
  - Pre-flight estimation per phase. Rejected: requires knowing the
    output volume of API calls before making them; not feasible for
    DataForSEO's variable-result endpoints. Could be added later as
    a "soft" estimate alongside the hard kill-switch.
  - Vendor-provided cost APIs (OpenAI's `usage` response field, etc.).
    Rejected as the only source: works after-the-fact, doesn't help
    if a single huge call would exceed the budget. Use as ground
    truth for the cost table tuning, not as the live guardrail.
  - Soft warning instead of hard abort. Rejected: warnings get
    ignored. Operators can raise the cap if they want.

- **Related:** [architecture.md → Cost Management](architecture.md#cost-management),
  `pipeline/utils/{dataforseo,openai_client,claude_client}.py` (to be
  written), `pipeline/utils/cost_tracker.py` (to be written).

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
