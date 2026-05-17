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

**Purpose:** Export `pending` clusters for human review (Google Sheet
or CSV). Import the reviewer's decisions back into Supabase, creating
rows in `topics` and `topic_keywords` for approved clusters.

Phase 12 has two distinct modes:

- **Export mode** (`--mode export`): read pending clusters, write a
  review sheet.
- **Import mode** (`--mode import`): read the reviewer's edited sheet,
  apply actions to the database.

### Export sheet structure

One row per cluster with `review_status = 'pending'`. Already-actioned
clusters (approved/rejected/merged/split) are excluded — re-running
export does not re-surface them.

| Column | Editable? | Purpose |
|---|---|---|
| `cluster_id` | No | Stable identifier; used to match rows on import. |
| `intent` | No | From clustering. |
| `confidence_score` | No | From ADR-004 formula. NULL for single-member clusters. |
| `member_count` | No | From clustering. |
| `total_search_volume` | No | Sum across members. |
| `member_keywords` | No | All cluster members, comma-separated. Truncated to first 30 if larger. |
| `suggested_subfolder` | Yes | From intent taxonomy. Reviewer can override. |
| `primary_keyword` | Yes | Pre-filled with `clusters.primary_keyword_candidate` (the centroid keyword). Reviewer can change to any member. |
| `review_action` | Yes | One of: `APPROVE`, `REJECT`, `MERGE`, `SPLIT`. Blank = `APPROVE` (the auto-approve default). |
| `merge_target_cluster_id` | Yes | Required iff `review_action = MERGE`. The `cluster_id` to merge this cluster into. |
| `split_into_groups` | Yes | Required iff `review_action = SPLIT`. Semicolon-separated keyword groups, each group comma-separated. Example: `kw1,kw2;kw3,kw4` becomes two new clusters. |
| `reviewer_notes` | Yes | Free text, copied to `clusters.reviewer_notes`. |

Clusters in `require_human_review_intents` (VENDOR/LEGAL/ACCESS for
retatrutide) and clusters with `confidence_score IS NULL` are always
included, even if their confidence is above
`confidence_auto_approve_threshold`.

Clusters with `confidence_score >= confidence_auto_approve_threshold`
AND not in `require_human_review_intents` are *not* exported — they
get auto-approved during import (see below).

### Edit actions and import semantics

Each action is applied inside a single transaction per cluster. If
import fails on row N, rows 1..N-1 remain committed and the failure is
logged to `pipeline_jobs.error_message` for resume.

**`APPROVE`** (or blank action):
1. Insert one `topics` row with the reviewer's `primary_keyword` and
   `suggested_subfolder`. `source_cluster_id = clusters.id`.
2. Insert `topic_keywords` rows for every cluster member with
   `role = 'primary'` for the chosen primary keyword, then `secondary`
   / `supporting` / `faq` assigned by Phase-12 heuristics (TBD —
   simplest version: top-3 by volume become `secondary`, rest become
   `supporting`).
3. Set `clusters.review_status = 'approved'`, `reviewed_at = now()`,
   `review_action = 'APPROVE'`.

**`REJECT`**:
1. No `topics` row created.
2. Set `clusters.review_status = 'rejected'`, `reviewed_at = now()`,
   `review_action = 'REJECT'`, copy `reviewer_notes`.

**`MERGE`**:
1. Validate that `merge_target_cluster_id` exists and belongs to the
   same site. Reject the row if not.
2. If the target was also marked `MERGE` to a third cluster, follow
   the chain (idempotent). If the chain has a cycle, reject the whole
   merge set and log to `pipeline_jobs`.
3. Set `clusters.review_status = 'merged'`, `merged_into_cluster_id =
   merge_target_cluster_id`.
4. The merge target's keywords are unioned with this cluster's
   keywords during *its own* APPROVE (the target row in the sheet is
   what creates the eventual topic).
5. If the merge target is itself marked `REJECT`, the merged keywords
   are also rejected — flag as a warning in `output_summary`.

**`SPLIT`**:
1. Parse `split_into_groups`. Validate every keyword named appears in
   the original cluster's members. Reject the row if not.
2. Set the original `clusters.review_status = 'split'`,
   `review_action = 'SPLIT'`.
3. For each parsed group, insert a new `clusters` row with
   `split_from_cluster_id = original_cluster_id`,
   `review_status = 'pending'`, copying intent/subfolder from the
   original. Move the relevant `cluster_members` rows to the new
   cluster.
4. The new pending clusters appear in the *next* Phase 12 export.

**Deleted rows**: a row present in the export but missing from the
imported sheet is treated as "no action" — the cluster stays
`pending`. This is intentional: deleting a row is not a clear signal
(was it deleted on purpose, or accidentally?). To reject a cluster,
the reviewer must explicitly set `review_action = REJECT`.

**Auto-approved clusters** (not in the export but eligible for direct
approval): during import, after the sheet is processed, run a final
sweep over `clusters` where `review_status = 'pending'` AND
`confidence_score >= confidence_auto_approve_threshold` AND `intent
NOT IN (require_human_review_intents)`. Apply `APPROVE` semantics to
each. Log count to `output_summary.auto_approved`.

### Inputs

- `clusters` rows where `review_status = 'pending'`.
- `cluster_members` joined to `raw_keywords` for the membership list
  and primary-keyword candidates.
- Config: `review.confidence_auto_approve_threshold`,
  `review.require_human_review_intents`,
  `review.google_sheets.sheet_id` (export destination, set after
  first export so subsequent exports update the same sheet).

### Outputs

**Export mode:**
- A Google Sheet (or local CSV if `google_sheets.sheet_id` is null).
- `review.google_sheets.sheet_id` populated in the site YAML config
  (and snapshotted into `pipeline_jobs.output_summary`) if a sheet was
  newly created.

**Import mode:**
- `topics` rows for approved + merge-target clusters.
- `topic_keywords` rows linking topics to their member keywords.
- `clusters.review_status` updated to terminal states.
- New `clusters` rows for SPLIT actions, with `review_status = 'pending'`.
- `pipeline_jobs.output_summary` counts:
  `{approved, rejected, merged, split, auto_approved, failed}`.

### Failure modes

- **Sheet edited while export was running**: detect via the
  `cluster_id` mismatch; refuse to import. Reviewer must re-export.
- **`merge_target_cluster_id` doesn't exist or belongs to another
  site**: row is logged and skipped. Other rows still import.
- **Merge cycle (A merges into B, B merges into A)**: detected
  in the merge-chain walk; all clusters in the cycle are skipped and
  logged.
- **SPLIT group references a keyword not in the cluster**: row is
  logged and skipped.
- **APPROVE without setting `primary_keyword`**: reject — the cluster
  must have an explicit primary keyword chosen by the reviewer.

### Idempotency

- **Export**: re-running export only exports clusters still in
  `pending`. Already-actioned clusters are excluded. Safe to re-run.
- **Import**: re-running import on the same sheet is a no-op — all
  clusters in the sheet are already in terminal states. Re-running
  with an edited sheet creates new actions only for clusters that
  were still `pending`.

### Configuration

`review.*` block in site YAML. Sheet creation requires
`GOOGLE_SHEETS_CREDENTIALS_PATH` env var set; without it, Phase 12
falls back to local CSV in `output/{site_slug}/clusters_review.csv`.

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
