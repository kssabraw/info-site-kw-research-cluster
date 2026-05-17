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

*To be documented when implemented.*

**Purpose:** Cluster keywords using HDBSCAN within each intent bucket
separately. Produce initial cluster set with confidence scores.

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
