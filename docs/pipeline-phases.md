# Pipeline Phases

Detailed specifications for each phase of the keyword discovery and
clustering pipeline. This document is populated as each phase is
implemented during the build.

For each phase, document:
- **Purpose** — what the phase accomplishes
- **Inputs** — Supabase tables read from, config sections consumed
- **Process** — high-level steps in order
- **Outputs** — Supabase tables written to
- **Expected cost** — typical API costs per run
- **Expected runtime** — typical wall-clock duration
- **Failure modes** — common failure cases and how they're handled
- **Idempotency behavior** — what happens on re-run
- **Configuration** — which YAML config values control behavior

---

## Phase 00: Concept Mapping

*To be documented when implemented.*

**Purpose:** LLM-generated tangential concept discovery to seed Phase 01
with terms beyond the user-provided primary seeds.

---

## Phase 01: Seed Expansion

*To be documented when implemented.*

**Purpose:** Expand primary seeds and tangential concepts via DataForSEO
`keyword_ideas` to produce initial keyword pool.

---

## Phase 02: SERP Fetching

*To be documented when implemented.*

**Purpose:** Fetch top 10 organic results for the highest-volume keywords
from Phase 01, capturing URLs, titles, PAA boxes, and related searches.

---

## Phase 03: URL and Domain Frequency Analysis

*To be documented when implemented.*

**Purpose:** Aggregate SERP data to identify hub URLs (appearing in
multiple seed SERPs) and competitor domains for downstream mining.

---

## Phase 04: URL-Level Keyword Mining

*To be documented when implemented.*

**Purpose:** Mine keywords from authoritative hub URLs via DataForSEO
`ranked_keywords`, filtered to positions 1-20 for relevance.

---

## Phase 05: Domain-Level Keyword Mining

*To be documented when implemented.*

**Purpose:** Mine ranking keywords from auto-derived competitor domains
via DataForSEO `keywords_for_site`.

---

## Phase 06: Relevance Filtering

*To be documented when implemented.*

**Purpose:** Apply niche-relevance gate (must-match terms + semantic
similarity) to all discovered keywords, marking included vs excluded.

---

## Phase 07: Volume Enrichment

*To be documented when implemented.*

**Purpose:** Validate and populate search volume data for all included
keywords via DataForSEO `keyword_overview`.

---

## Phase 08: Intent Classification

*To be documented when implemented.*

**Purpose:** Classify each keyword's intent using Haiku 4.5 with the
site's intent taxonomy. Map intent to suggested subfolder.

---

## Phase 09: Embedding Generation

*To be documented when implemented.*

**Purpose:** Generate vector embeddings for all included keywords using
OpenAI text-embedding-3-large with enriched input text.

---

## Phase 10: HDBSCAN Clustering

**Purpose:** Cluster keywords using HDBSCAN within each intent bucket
separately. Produce initial cluster set with confidence scores.

**Inputs:**
- `raw_keywords` filtered to `is_included = TRUE`, grouped by `primary_intent`.
- `keyword_embeddings.embedding` (3072-dim halfvec).
- `keyword_serps` for the SERP-overlap component of confidence (optional;
  if missing, the fallback formula is used).
- Config: `clustering.min_cluster_size`, `clustering.min_samples`,
  `clustering.cluster_selection_epsilon`, `clustering.thin_bucket_threshold`.

**Process:**
1. For each intent bucket independently:
   1. Pull the intent's keywords and their embeddings.
   2. **If the bucket has fewer than `thin_bucket_threshold` keywords:**
      skip HDBSCAN. Each keyword becomes a single-member cluster with
      `confidence_score = NULL`. See ADR-005 — protects rare intents
      (VENDOR/LEGAL/ACCESS) from being dumped into HDBSCAN noise.
   3. **Otherwise:** run HDBSCAN with the config parameters.
      - Keywords labeled `-1` (noise) become single-member clusters with
        `confidence_score = NULL` so they show up in human review.
      - For each multi-member cluster, compute the three confidence
        components and the weighted sum per ADR-004.
2. Insert into `clusters` and `cluster_members`. Set
   `clusters.clustering_run_id` to the current `pipeline_jobs.id`.
3. Mark every cluster in `require_human_review_intents` (from YAML) as
   `review_status = 'pending'` regardless of confidence.

**Outputs:**
- `clusters` (one row per cluster, plus single-member rows for noise).
- `cluster_members` (junction rows, one per member with
  `similarity_score` = cosine distance from cluster centroid,
  `is_centroid` for the closest member).
- `pipeline_jobs.output_summary` includes per-intent cluster counts,
  per-intent noise rate, and a list of intents that fell below
  `thin_bucket_threshold` and were not clustered.

**Confidence score formula (canonical source: ADR-004):**

```
confidence_score = 0.50 * intra_similarity
                 + 0.30 * intent_agreement
                 + 0.20 * serp_overlap
```

Components:

- `intra_similarity`: mean pairwise cosine similarity of member
  embeddings, clipped to [0, 1].
- `intent_agreement`: mean of `raw_keywords.intent_confidence` for
  members.
- `serp_overlap`: mean pairwise Jaccard of top-10 SERP URL sets for
  members.

Fallback (no SERPs available for members):

```
confidence_score = 0.625 * intra_similarity + 0.375 * intent_agreement
```

Single-member clusters: `confidence_score = NULL`. These always go to
human review.

**Failure modes:**
- HDBSCAN dumps everything to noise (`-1`): cluster count is 0 for that
  intent bucket; all keywords become single-member clusters. Surface
  the noise rate in `output_summary` so review effort is predictable.
- Embedding model version drift across runs: members of the same
  cluster may have been embedded by different model versions if
  Phase 09 was re-run with a new model. Phase 10 must refuse to cluster
  members that don't share `keyword_embeddings.model_version` — fail
  fast rather than silently mixing.

**Idempotency:** Re-running deletes prior clusters and members for the
current site (cascading from `clusters`), then re-inserts. Approved
topics in the `topics` table are not affected (topics keep their own
keyword bundles via `topic_keywords`).

**Configuration:** `clustering.*` block in site YAML.

---

## Phase 11: SERP Overlap Refinement

*To be documented when implemented.*

**Purpose:** Refine clusters using SERP overlap analysis. Merge clusters
sharing high SERP overlap; split clusters with low internal SERP overlap.

---

## Phase 12: Review Export and Import

*To be documented when implemented.*

**Purpose:** Export clusters for human review (Google Sheet or CSV).
Import approved decisions back to Supabase, populating topics table.

---

## How This Document Is Maintained

This document is updated by Claude Code (or developers) during pipeline
implementation. When a phase is implemented:

1. Replace "To be documented when implemented" with full specification
2. Include actual implementation details, not speculation
3. Note any deviations from the original design with reasoning
4. Document failure modes discovered during testing
5. Record actual costs and runtimes from real runs

When phases are modified later:

1. Update the spec to reflect current behavior
2. Note breaking changes that affect other phases
3. Update Cross-references if phase interfaces changed
