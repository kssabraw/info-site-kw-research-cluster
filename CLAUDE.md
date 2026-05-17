# Multi-Tenant Keyword Discovery & Clustering Pipeline

## What This Project Is

A multi-tenant keyword discovery and clustering pipeline that produces
approved topic plans for content site generation. Built to scale across
a portfolio of niche-specific content sites.

Each site has its own configuration, seeds, and clusters, but shares
the same engine. New sites are added by creating a new config file,
not by modifying pipeline code.

## Current Status

Update the checklist below as work progresses. Active site at top.

### Active Site: retatrutide

Phase progress:
- [x] Project scaffold and database schema
- [ ] Phase 00: Concept mapping
- [ ] Phase 01: Seed expansion
- [ ] Phase 02: SERP fetching
- [ ] Phase 03: URL + domain frequency analysis
- [ ] Phase 04: URL-level keyword mining
- [ ] Phase 05: Domain-level keyword mining
- [ ] Phase 06: Relevance filtering
- [ ] Phase 07: Volume enrichment
- [ ] Phase 08: Intent classification
- [ ] Phase 09: Embedding generation
- [ ] Phase 10: HDBSCAN clustering
- [ ] Phase 11: SERP overlap refinement
- [ ] Phase 12: Review export and import
- [ ] Approved topics exported to topics table

## Architecture

See `docs/architecture.md` for full system design. Key principles:

- **Multi-tenant Supabase from day one** — every table has `site_id`
  column (BIGINT, references sites.id). No exceptions.
- **Phase-based pipeline** — each phase is independently runnable,
  reads input from Supabase, writes output to Supabase, doesn't share
  memory state with other phases.
- **Config-driven** — niche-specific behavior (seeds, relevance terms,
  thresholds, taxonomies) lives in `config/sites/{slug}.yaml`. Pipeline
  code never hardcodes niche specifics.
- **Job tracking** — every phase run logs to `pipeline_jobs` table at
  start and end with config snapshot and output stats.
- **Supabase as source of truth** — no intermediate CSV/JSON files
  between phases. Database state is canonical.

## Stack

- **Python 3.11+** managed via `uv`
- **Supabase** (Postgres + pgvector for embeddings)
- **DataForSEO API** for keyword discovery and SERPs
- **OpenAI API** (text-embedding-3-large for clustering)
- **Anthropic API** (Haiku 4.5 for intent classification, Sonnet/Opus
  for concept mapping)
- **HDBSCAN** for clustering algorithm

## Pipeline Phases

See `docs/pipeline-phases.md` for detailed specs of each phase.

00. **Concept mapping** — LLM generates tangential concepts for the niche
01. **Seed expansion** — DataForSEO keyword_ideas on primary + tangential seeds
02. **SERP fetching** — Top 10 organic results for highest-volume keywords
03. **URL + domain frequency analysis** — Auto-derive competitor list from SERPs
04. **URL-level keyword mining** — ranked_keywords on hub URLs, positions 1-20
05. **Domain-level keyword mining** — keywords_for_site on top competitor domains
06. **Relevance filtering** — Must-match terms + semantic similarity threshold
07. **Volume enrichment** — keyword_overview for final volume/CPC validation
08. **Intent classification** — Haiku assigns each keyword to intent taxonomy
09. **Embedding generation** — OpenAI embeddings on enriched keyword text
10. **HDBSCAN clustering** — Cluster within each intent bucket separately
11. **SERP overlap refinement** — Split/merge clusters based on SERP overlap
12. **Review export and import** — Human-in-the-loop approval via Google Sheet

## Critical Conventions

When writing or modifying code, follow these rules:

- **Always pass site_id explicitly** through function calls. Never derive
  it from "current context" or globals.
- **All database operations** go through `pipeline/utils/database.py`,
  not raw SQL scattered through phase modules.
- **All API clients** are in `pipeline/utils/` (`dataforseo.py`,
  `openai_client.py`, `claude_client.py`). Phases call these utilities,
  don't construct API requests directly.
- **Config loading** goes through `pipeline/utils/config.py`. Never
  read YAML files directly from phase modules.
- **Job tracking is required** — every phase wraps its work in a
  `pipeline_jobs` record. Use the `@track_job` decorator.
- **Idempotency** — phases should be safely re-runnable. If a phase has
  already produced output for a site, re-running should either skip or
  cleanly replace, never duplicate.

## Database Schema Summary

Full schema in `docs/database-schema.md`. Core tables:

- `sites` — Multi-tenant root; config in JSONB
- `pipeline_jobs` — Run tracking per phase
- `raw_keywords` — All discovered keywords (with site_id, discovery_method)
- `keyword_serps` — SERP results for keywords
- `keyword_embeddings` — pgvector embeddings (1024 or 3072 dim)
- `tangential_concepts` — Phase 00 output
- `clusters` — Clustering output before review
- `topics` — Approved clusters ready for article generation
- `topic_keywords` — Junction table: which keywords belong to which topic
- `topic_relationships` — Pillar/leaf hierarchy

## Project Structure

clustering-tool/
├── CLAUDE.md                       # This file
├── PROJECT_BRIEF.md                # Architecture decisions and rationale
├── README.md                       # Setup and run instructions
├── pyproject.toml                  # Python deps via uv
├── .env.example                    # Required env vars template
├── docs/
│   ├── architecture.md
│   ├── pipeline-phases.md
│   ├── database-schema.md
│   └── decisions-log.md            # ADRs
├── config/
│   └── sites/
│       └── {site_slug}.yaml        # Per-site config
├── pipeline/
│   ├── init.py
│   ├── run.py                      # CLI entry point
│   ├── phases/                     # 12 phase modules
│   └── utils/                      # Database, API clients, config
├── schema/
│   └── schema.sql                  # Supabase schema DDL
└── output/                         # Local exports (Google Sheets CSVs, etc)

## How to Run

```bash
# One-time setup
uv sync
cp .env.example .env  # then fill in API keys

# Deploy schema to Supabase (one-time)
# Run schema/schema.sql against your Supabase project

# Run a single phase for a site
uv run python -m pipeline.run --site {slug} --phase 01

# Run all phases sequentially
uv run python -m pipeline.run --site {slug} --phase all

# Run phases with custom range
uv run python -m pipeline.run --site {slug} --phase 01-07
```

## Adding a New Site

To launch keyword discovery for a new niche:

1. Create `config/sites/{new_slug}.yaml` with primary seeds, niche match
   terms, thresholds (use existing site config as template)
2. Insert site record in `sites` table (slug, domain, config from YAML)
3. Run pipeline: `uv run python -m pipeline.run --site {new_slug} --phase all`
4. Review clusters in Google Sheet export from Phase 12
5. Import approved decisions back to topics table

No pipeline code changes required.

## Configuration Schema

Each site's YAML config follows this structure:

```yaml
site_slug: string                    # Must match sites.slug in DB
site_id: integer                     # Set after first DB insert

discovery:
  primary_seeds: [string, ...]       # 10-15 seed keywords
  semantic_relevance_threshold: float  # 0.0-1.0, typically 0.65
  volume_minimum: integer            # Skip keywords below this
  max_keywords_for_serp_fetch: int   # Cap SERP API costs
  auto_competitor_count: int         # Top N domains auto-derived
  manual_competitor_domains: [str]   # Optional additions

filtering:
  niche_match_terms: [string, ...]   # Must-contain relevance terms
  exclusion_terms: [string, ...]     # Hard exclusions

intent_taxonomy:
  template: string                   # References templates/intent_taxonomies/
  custom_overrides: dict             # Site-specific intent rules

clustering:
  embedding_model: string            # e.g., text-embedding-3-large
  min_cluster_size: int              # HDBSCAN parameter
  target_cluster_count: int          # Soft target after refinement

review:
  confidence_auto_approve_threshold: float  # 0.0-1.0
  require_human_review_intents: [str]       # Intents that always need review
```

## What to Read Before Working On

- **New phase implementation**: `docs/pipeline-phases.md`
- **Schema changes or queries**: `docs/database-schema.md`
- **Architectural questions**: `docs/architecture.md`
- **"Why was X decided?"**: `docs/decisions-log.md`
- **Site-specific values**: `config/sites/{slug}.yaml`

## What This Tool Is NOT

- **Not a content generator** — produces topic plans, not articles.
  Article generation is a separate downstream pipeline.
- **Not a SaaS product** — internal tool, may grow into team tool later.
- **Not multi-language** — English/US market focus for current sites.
- **Not real-time** — batch jobs, phase runs take minutes to hours.
- **Not a Semrush replacement** — focused on a specific clustering
  workflow, not general SEO research.

## End-of-Session Protocol

Before ending a Claude Code session:

1. Update the status checklist above with completed work
2. Add any new architectural decisions to `docs/decisions-log.md`
3. Update `docs/pipeline-phases.md` for any phases implemented or modified
4. Commit changes with a clear message
5. Note any open questions or blockers in a session summary

## Phase Completion Contract

A pipeline phase is not "done" — and its checkbox above must not be
ticked — until **all three** of the following are true in the same
commit:

1. The status checkbox in this file is ticked.
2. The corresponding `docs/pipeline-phases.md` **OPEN** block is
   replaced with a **Specified** entry covering Purpose, Inputs,
   Process, Outputs, Expected cost, Expected runtime, Failure modes,
   Idempotency, and Configuration.
3. Any new design decisions made while implementing the phase are
   captured as ADRs in `docs/decisions-log.md` and linked from the
   spec.

Reviewers (human or Claude) should reject any commit that ticks a
checkbox without also satisfying (2) and (3). The `**OPEN**` marker
exists precisely to make incomplete specs visually conspicuous — it is
not a stable state.

Equivalent rule for `docs/architecture.md`: the **OPEN** sections
there are unanswered questions tied to specific code modules (e.g.,
`pipeline/utils/database.py`, `pipeline/utils/config.py`). The first
commit that creates one of those modules must resolve the
corresponding **OPEN** section in the same commit.
