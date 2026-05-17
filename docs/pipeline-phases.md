# Pipeline Phases

Per-phase specifications. This document is the canonical contract
between phases — what each one reads, writes, and assumes.

## How to read this doc

Each phase below is either:

- **Specified** — every section below is filled in. Treat as current
  truth for downstream phases.
- **OPEN** — a short list of unanswered questions the first
  implementing commit must replace. The presence of OPEN means the
  contract for that phase is not yet pinned and downstream phases
  cannot rely on its outputs.

When implementing a phase, replace its OPEN block with a fully filled
**Specified** entry covering:

- **Purpose** — what the phase accomplishes (one paragraph)
- **Inputs** — Supabase tables read, config keys consumed
- **Process** — numbered steps
- **Outputs** — Supabase tables written, `pipeline_jobs.output_summary` keys
- **Expected cost** — typical API spend per run
- **Expected runtime** — typical wall-clock duration
- **Failure modes** — known failure categories and handling
- **Idempotency** — what `--force` re-run does
- **Configuration** — YAML keys that control behavior

Specs come from running the phase against real data, not from
speculation. If you haven't run it, don't write the spec — leave the
OPEN block and let the next implementer do it.

## Cross-cutting contracts every phase must honor

These apply to every phase regardless of its individual spec.

- **fetch vs derive (ADR-015):** every phase separates work that
  costs money (`fetch`) from work that only reads existing rows
  (`derive`). `--rederive` mode runs only the latter. Pure-fetch
  phases raise `NotImplementedError` on `--rederive`; pure-derive
  phases run normally.
- **Per-batch commit on iteration (ADR-016):** any phase iterating
  over external API calls commits per-batch (sizes in ADR-016).
  Resume after partial failure via
  `pipeline/utils/database.py::unprocessed_for_phase(site_id, phase_name)`,
  which returns the rows still lacking this phase's output.
- **CostTracker (ADR-014):** every API call charges the run's
  CostTracker before issuing. `CostBudgetExceeded` is fatal to the
  current run; partial batches remain committed.
- **`@track_job` decorator (CLAUDE.md R4):** every `def run(...)` in
  `pipeline/phases/` is decorated. The decorator owns the
  `pipeline_jobs` lifecycle (status transitions, output_summary,
  error capture).

If you find yourself writing phase-specific logic for any of these,
stop — promote the logic to the shared utility and call it from
every phase.

---

## Phase 00: Concept Mapping

**Purpose:** LLM-generated tangential concept discovery to seed Phase 01
with terms beyond the user-provided primary seeds.

**OPEN** — answer when implementing:

1. Which Claude model — Sonnet 4.6 or Opus 4.7? (Strategic doc says
   Sonnet for cheaper tasks; concept mapping is one-shot per site, so
   cost is small either way.)
2. Prompt structure — single call returning a JSON list, or one call
   per `concept_mapping.categories_template` category?
3. How does volume validation work (`volume_validation_required: true`
   in YAML)? DataForSEO call per concept, or batched?
4. Output schema in `tangential_concepts`: what does `category` actually
   contain — strings matching `categories_template`, or free-form?

---

## Phase 01: Seed Expansion

**Purpose:** Expand primary seeds and tangential concepts via DataForSEO
`keyword_ideas` to produce initial keyword pool.

**OPEN** — answer when implementing:

1. Are tangential concepts from Phase 00 (with `promoted_to_seeds = TRUE`)
   passed as additional seeds, or does Phase 01 always query both
   `discovery.primary_seeds` AND `tangential_concepts` together?
2. DataForSEO `keyword_ideas` returns up to N results per seed. What's
   N, and is there a per-seed cap?
3. Dedup strategy when two seeds return the same keyword — keep both
   with merged `discovery_source`, or first-write-wins?
4. `raw_keywords.discovery_method` value: `'seed_expansion'` or more
   granular (`'seed_primary'` vs `'seed_tangential'`)?

---

## Phase 02: SERP Fetching

**Purpose:** Fetch top 10 organic results for the highest-volume keywords
from Phase 01, capturing URLs, titles, PAA boxes, and related searches.

**OPEN** — answer when implementing:

1. Which keywords get SERPs? Top N by volume where N =
   `discovery.max_keywords_for_serp_fetch` (3000 in retatrutide YAML)?
   Confirm the cutoff is volume-based vs random sample.
2. DataForSEO endpoint: `serp/google/organic/live/advanced` or
   `serp/google/organic/task_post`? Batch vs single?
3. Fields landing in `keyword_serps.serp_features` JSONB — PAA, related
   searches, featured snippet, anything else?
4. Re-fetch policy: if a keyword already has SERPs, skip or refresh?
   (Default to skip for idempotency, but document.)

---

## Phase 03: URL and Domain Frequency Analysis

**Purpose:** Aggregate SERP data to identify hub URLs (appearing in
multiple seed SERPs) and competitor domains for downstream mining.

**OPEN** — answer when implementing:

1. `serp_urls.mining_priority` thresholds: schema comment says
   `high (10+), medium (5-9), low (3-4), skip (<3)`. Confirm or revise.
2. `serp_urls.mining_depth` per priority — schema comment says
   `100/50/20`. Confirm.
3. Competitor selection for `serp_domains.is_competitor`: top N domains
   by frequency where N = `discovery.auto_competitor_count`?
4. How are `discovery.manual_competitor_domains` merged in — flagged
   `is_competitor=TRUE` with a special marker, or just unioned with the
   auto-derived list?

---

## Phase 04: URL-Level Keyword Mining

**Purpose:** Mine keywords from authoritative hub URLs via DataForSEO
`ranked_keywords`, filtered to positions 1-20 for relevance.

**OPEN** — answer when implementing:

1. Mine `serp_urls` where `mining_priority IN ('high', 'medium', 'low')`,
   skipping `'skip'`. Confirm.
2. Per-URL cap = `serp_urls.mining_depth`. What position cutoff —
   positions 1-20, or all positions then filter?
3. Output goes to `discovered_keywords` (staging), not directly to
   `raw_keywords`. When does Phase 06 promote?
4. Rate limiting against DataForSEO at hub-URL scale — how does the
   API client handle bursts?

---

## Phase 05: Domain-Level Keyword Mining

**Purpose:** Mine ranking keywords from auto-derived competitor domains
via DataForSEO `keywords_for_site`.

**OPEN** — answer when implementing:

1. Per-domain cap — schema doesn't specify. Hardcoded or per-domain
   config?
2. `keywords_for_site` can return enormous result sets for large
   competitors. What's the filter — position cap, volume floor, or
   top-N by traffic?
3. `discovered_keywords.source_type` is `'domain_mining'`,
   `source_identifier` is the domain. Confirm.
4. Same staging-table semantics as Phase 04 — output to
   `discovered_keywords`, not directly to `raw_keywords`.

---

## Phase 06: Relevance Filtering

**Purpose:** Apply niche-relevance gate to all discovered keywords,
marking included vs excluded. Two paths by source — see ADR-011.

**Partially specified (ADR-011):**

- **Source split:** `raw_keywords.tangential_distance` decides the
  path. `0` = direct discovery (primary_seeds, URL mining, domain
  mining). `>= 1` = tangential discovery (Phase 00 concepts and their
  expansions).
- **Direct-discovery path:** must contain at least one of
  `filtering.niche_match_terms` (any-of, OR) AND clear
  `discovery.semantic_relevance_threshold` against the site's niche
  embedding.
- **Tangential path:** semantic similarity threshold only.
- **Both paths:** `filtering.exclusion_terms` is a hard reject (any
  match → excluded).
- **Exclusion writes:** `is_included = FALSE` plus
  `exclusion_reason IN ('niche_match', 'semantic_threshold',
  'exclusion_term')`. See ADR-007 — `tier` is not touched here.

**OPEN** — remaining questions for implementation:

1. Does the filter operate on `raw_keywords` (already promoted from
   `discovered_keywords` by an earlier sub-step) or on the
   `discovered_keywords` staging table directly?
2. Promotion from `discovered_keywords` to `raw_keywords`: when and
   how (this phase, or a separate Phase 05b)?
3. The site's niche embedding (one vector per site) computed from
   `site_metadata.niche_description`: stored where? Options: compute
   on-the-fly each Phase 06 run; cache in `sites.runtime_state ->
   'phase_06' -> 'niche_embedding'`; or add a typed column
   `sites.niche_embedding HALFVEC(3072)`. Pick at implementation.
4. Per-source weighting: should Phase 04 (URL mining) keywords with
   high `source_url_frequency` get a more lenient threshold, or is
   the binary threshold sufficient?

---

## Phase 07: Volume Enrichment

**Purpose:** Validate and populate search volume data for all included
keywords via DataForSEO `keyword_overview`.

**OPEN** — answer when implementing:

1. Re-validate every keyword's volume, or only those missing
   `search_volume`? (Phase 01 and 04/05 already populated volumes from
   different DataForSEO endpoints; this phase exists to reconcile.)
2. Disagreement handling — if Phase 01 said volume=1000 and Phase 07
   says volume=500, which wins, and is the prior value preserved
   anywhere?
3. Batch size against `keyword_overview` endpoint.
4. Cost guardrail interaction — `keyword_overview` is one of the
   pricier endpoints; how does this phase respect `MAX_RUN_COST_USD`?

---

## Phase 08: Intent Classification

**Purpose:** Classify each keyword's intent using Haiku 4.5 with the
site's intent taxonomy. Map intent to suggested subfolder.

**OPEN** — answer when implementing:

1. Prompt structure: pass the full `intent_taxonomy` block from YAML
   into every call, or summarize?
2. Batching: one keyword per call, or N keywords per call returning a
   JSON list?
3. `intent_confidence` from the model: how is it elicited (ask the
   model directly, or compute from logprobs / token consistency)?
4. Output also populates `raw_keywords.suggested_subfolder` from the
   intent → subfolder mapping in the YAML. What happens for an
   `EDUCATIONAL` keyword whose top SERP results suggest it belongs in
   `/conditions/`? (Reviewer fix in Phase 12, or override here?)
5. Multi-intent keywords: pick top-1, or store top-k with a "primary"
   flag and let Phase 10 cluster on primary?

---

## Phase 09: Embedding Generation

**Purpose:** Generate vector embeddings for all included keywords using
OpenAI text-embedding-3-large with enriched input text.

**OPEN** — answer when implementing:

1. "Enriched input text" composition: `keyword + intent + top-3 SERP
   titles`? Just `keyword`? The doc isn't specific. Define the exact
   string template.
2. `keyword_embeddings.model_version`: format like
   `text-embedding-3-large@3072` (per ADR-002)? Pin this so Phase 10's
   model-version-drift check has a stable string to compare.
3. Batch size against OpenAI's embeddings endpoint.
4. Re-embed policy: if a keyword already has an embedding with the
   current `model_version`, skip. If `model_version` differs, replace.
   Confirm.
5. Halfvec conversion: OpenAI returns float32. Where is the cast to
   `halfvec(3072)` performed — in Python before insert, or via the
   pgvector driver?

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

**Purpose:** Refine clusters using SERP overlap analysis. Merge clusters
sharing high SERP overlap; split clusters with low internal SERP overlap.

**OPEN** — answer when implementing:

1. Merge criterion: `serp_refinement.merge_threshold` (0.7) is the
   Jaccard of top-10 URLs *between* two clusters' centroid keywords,
   or pairwise across all members? Define precisely.
2. Split criterion: `serp_refinement.split_threshold` (0.3) is what
   exactly — mean pairwise Jaccard within cluster, or fraction of
   members with low cohesion?
3. When clusters are merged: keep the higher-confidence cluster's id
   and absorb the other (use `merged_into_cluster_id`), or create a
   new cluster? The schema supports both via
   `merged_into_cluster_id` / `split_from_cluster_id`. Pick one
   convention.
4. Confidence recomputation after refinement: re-run the ADR-004
   formula on the new membership? (Yes is the obvious answer; confirm
   and document the recompute as part of this phase.)
5. Interaction with thin-bucket clusters (ADR-005): single-member
   clusters can't be split (member_count=1). Can they be merged into
   a larger cluster, or are they preserved through Phase 11 untouched
   for human review?

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
   `suggested_subfolder`. `source_cluster_id = clusters.id`. Inherit
   `ymyl_risk`, `regulatory_sensitivity`, and `freshness_tier` from
   the YAML `intent_taxonomy.{cluster.intent}` block — these are
   per-intent properties, not per-topic decisions, so the YAML is the
   source of truth. If the YAML omits a flag for that intent, the
   `topics` column stays NULL.
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
  `review.google_sheets.worksheet_name`.
- Runtime state: `sites.runtime_state -> 'phase_12' ->
  'google_sheets_sheet_id'` (read on subsequent exports; written by
  the first export). YAML stays immutable — see ADR-010.

### Outputs

**Export mode:**
- A Google Sheet (or local CSV if `runtime_state.phase_12.google_sheets_sheet_id`
  is null AND `GOOGLE_SHEETS_CREDENTIALS_PATH` is unset).
- `sites.runtime_state.phase_12.google_sheets_sheet_id` populated if a
  sheet was newly created. Also snapshotted into
  `pipeline_jobs.output_summary` so the job record alone tells you
  which sheet a run produced.

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

When a phase is implemented:

1. Replace its **OPEN** block with a fully-filled **Specified** entry
   (Purpose, Inputs, Process, Outputs, Expected cost, Expected runtime,
   Failure modes, Idempotency, Configuration).
2. Specs come from running the phase against real data, not speculation.
3. Note any deviations from the original design with reasoning. If the
   deviation reflects a decision worth preserving, add an ADR in
   `decisions-log.md` and link from the spec.
4. Update the corresponding CLAUDE.md status checkbox in the same
   commit.

When phases are modified later:

1. Update the spec to reflect current behavior in the same commit.
2. Note breaking changes that affect other phases at the top of the
   modified spec.
3. Update cross-references if phase interfaces changed.

**Phase completion contract.** A pipeline phase is not "done" until:

- The CLAUDE.md status checkbox is ticked.
- The pipeline-phases.md OPEN block is replaced with a Specified entry.
- Any new ADRs are linked from the spec.

Reviewers (human or Claude) should reject a phase-completion commit
that doesn't satisfy all three.
