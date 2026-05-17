# Project Brief: Multi-Tenant Keyword Discovery & Clustering Pipeline

## Purpose

This document captures the architectural decisions, scaling philosophy,
and design constraints behind the keyword discovery and clustering
pipeline. It exists to answer "why was this built this way?" for future
contributors (including future versions of yourself).

For *what* the pipeline does, see `CLAUDE.md`.
For *how* each phase works, see `docs/pipeline-phases.md`.
For specific decisions and tradeoffs, see `docs/decisions-log.md`.

---

## Project Goal

Build a repeatable keyword discovery and topic clustering process that
scales across a portfolio of content sites, where each site targets a
distinct niche but shares the same underlying engine.

The pipeline produces approved **topic plans** (not keywords, not articles)
that downstream content generation systems consume. A "topic" is a
clustered set of related keywords that maps to a single content piece
with a primary keyword, supporting keywords, and an assigned subfolder.

## What Success Looks Like

For each site the pipeline runs against:

- ~500 approved topics ready for article generation
- Each topic mapped to a subfolder in a defined site taxonomy
- Each topic has a primary keyword + bundle of supporting keywords
- Each topic has confidence scoring and review status
- The pipeline run is reproducible from config + a fresh database

For the pipeline as a whole:

- Adding a new site requires creating one YAML config file, not editing
  pipeline code
- Pipeline phases are independently runnable, so a failure mid-pipeline
  doesn't require restarting from scratch
- The system can transition from solo CLI usage to a multi-user team
  tool without rewriting core pipeline logic

---

## Core Architecture Principles

### 1. Multi-Tenant From Day One

Every database table has a `site_id` column referencing `sites.id`.
Queries always filter by `site_id`. Row Level Security policies enforce
isolation at the database layer.

**Why this matters:** Retrofitting multi-tenancy is expensive. Adding
`site_id` to every existing row, updating every query, and migrating
data across sites is a multi-day operation. Adding the column from day
one costs ~15 minutes.

**The cost of doing this wrong:** When the second site launches, you
either fork the codebase (technical debt forever) or do a painful
migration (lost engineering time).

### 2. Configuration Over Code

Niche-specific behavior lives in YAML configs, not in Python code.
The pipeline reads `config/sites/{slug}.yaml` and behaves accordingly.

What goes in config:
- Primary seed keywords
- Niche relevance terms
- Confidence thresholds
- Intent taxonomies (with examples specific to the niche)
- Embedding model selection
- Cluster sizing targets
- Review requirements

What stays in code:
- DataForSEO API integration
- HDBSCAN clustering algorithm
- Embedding generation
- Database operations
- Pipeline orchestration

**Why this matters:** When you launch site #2, the pipeline code stays
identical. You create a new YAML and run the same engine against it.
This is the difference between "we have a pipeline" and "we have a
product that scales."

**The cost of doing this wrong:** Hardcoded niche values mean every
new site requires code changes, which means every new site requires a
developer, which means scaling stops being repeatable.

### 3. Phase-Based, Database-Mediated

The pipeline is structured as 12 discrete phases (00 through 12). Each
phase:

- Reads its input from Supabase tables
- Performs its specific transformation
- Writes its output to Supabase tables
- Can be run independently of other phases
- Does not share in-memory state with other phases

**Why this matters:** This architecture is the same whether the trigger
is a CLI command, a Python function call, or an HTTP endpoint. When you
later build a web UI, the UI calls the same phase functions. No
rewriting required.

**The cost of doing this wrong:** Monolithic scripts with shared memory
state can't be easily exposed as services, can't be partially re-run,
and can't be parallelized across sites.

### 4. Job Tracking From Day One

Every phase run logs to `pipeline_jobs` with:
- Site ID
- Phase name
- Status (queued/running/completed/failed)
- Started/completed timestamps
- Config snapshot used
- Output summary statistics
- Error messages if applicable

**Why this matters:** Even for solo CLI usage, this enables comparing
runs ("which parameter set produced 500 clusters?"), debugging failures,
and reproducing historical results. When the team UI exists, the same
table powers status displays.

**The cost of doing this wrong:** Without job tracking, you can't tell
what produced your current data. Reproducing a successful run becomes
guesswork.

### 5. Supabase as Source of Truth

No intermediate CSV/JSON files between phases. All state lives in
Supabase tables. Local files are only used for:

- One-time exports for human review (e.g., Google Sheets)
- Configuration (YAML files in git)
- Logs (when database logging is impractical)

**Why this matters:** The eventual team UI needs to read pipeline state
from somewhere. If state lives in scattered local files, the UI can't
see it. If it lives in Supabase from day one, the UI just queries the
same tables.

**The cost of doing this wrong:** File-based intermediate state can't
be queried, can't be displayed in dashboards, can't be reasoned about
across runs, and has no natural multi-tenancy boundary.

---

## What This Pipeline Is NOT

Equally important to define what we're not building.

### Not a Content Generator

The pipeline produces topic plans, not articles. Article generation
is a separate downstream system with different concerns (source
grounding, fact-checking, citation validation, freshness tracking).

### Not a SaaS Product

This is an internal tool. It may evolve into a team tool for internal
VAs, but it is not designed for external customers. No billing, no
white-labeling, no support infrastructure, no marketing site.

### Not a Semrush Replacement

The pipeline is built for a specific clustering workflow. It is not a
general-purpose SEO research tool. It doesn't replace keyword research
UIs, competitive analysis dashboards, or rank tracking. It has one job:
turn raw keyword data into approved topic plans.

### Not Real-Time

Pipeline phases are batch jobs. A typical full run takes minutes to
hours. The clustering and review workflow assumes human-in-the-loop
review, not instant results.

### Not Multi-Language (Yet)

Current pipeline assumes English/US market. Multi-language support
would require:
- Per-language embedding models (or multilingual models)
- Per-language intent classification prompts  
- Language detection in the keyword pool
- Language-specific SERP fetching (location/language params)

These are deferred until needed. Current sites do not require them.

### Not Real-Time Web Search Dependent

The pipeline pulls keyword data via DataForSEO API at known points in
the workflow. It does not require live web search during clustering.
This makes runs reproducible and cacheable.

---

## Scaling Philosophy

The project assumes a portfolio of N sites over time, where N grows
gradually. Architectural decisions favor:

**Compounding infrastructure investment**
The cost of launching site #N decreases as N grows. The discovery
pipeline, clustering algorithm, schema, and review tools are shared
infrastructure. Per-site cost is dominated by API calls, not engineering.

**Templates over duplication**
When patterns emerge across sites (intent taxonomies, niche category
structures, common subfolder layouts), they become templates referenced
by site configs. The first instance of a pattern is inline; the second
instance triggers refactoring into a template.

**Lazy abstraction**
Abstractions are added when there are at least two concrete instances
to compare. The first site implements things directly. The second site
either reuses the first's patterns (validation) or reveals the need for
abstraction (refactoring opportunity).

**Skeptical of premature optimization**
A 100-line phase that does one thing in the most obvious way is better
than a 500-line phase with sophisticated error handling that may never
be exercised. Build the simplest thing that works at current scale,
upgrade when constraints actually bite.

---

## What We Considered and Rejected

Documenting the alternatives that were considered helps future
contributors understand why obvious-looking approaches weren't chosen.

### Considered: Semrush for keyword discovery

Rejected in favor of DataForSEO-only. Reasoning:
- Semrush requires manual CSV exports (breaks programmatic workflow)
- Semrush subscription cost is non-trivial for a single project
- DataForSEO covers ~90-95% of relevant keyword discovery for tight
  niches at a fraction of the cost
- DataForSEO API access scales naturally across sites; Semrush UI
  workflow doesn't

See `docs/decisions-log.md` ADR-001 for details.

### Considered: RoBERTa/sentence-transformers for embeddings

Rejected in favor of OpenAI text-embedding-3-large. Reasoning:
- ~10 point MTEB gap on clustering tasks
- Modern models have seen current technical terminology that older
  embedding models haven't
- Cost difference at our scale is negligible (~$0.04 vs $0)
- Engineering time to self-host outweighs API cost

See `docs/decisions-log.md` ADR-002 for details.

### Considered: Cluster first, then classify intent

Rejected in favor of classify-first, cluster-within-intent. Reasoning:
- Mixed-intent clusters produce bad article assignments
- Per-intent clustering uses HDBSCAN parameters tuned to that intent's
  typical cluster size and density
- Subfolder assignment becomes trivial (intent maps directly to subfolder)
- Cost increase is small (~$1 in Haiku API calls)

### Considered: Recursive SERP mining

Rejected in favor of single-level mining only. Reasoning:
- Each recursion level drifts further from seed niche
- Level 2+ produces keyword pollution that costs more to filter than
  the value it adds
- URL frequency weighting captures most of the value of recursion
  without the drift

### Considered: Live web search in pipeline

Rejected in favor of DataForSEO batch fetching. Reasoning:
- Pipeline must be reproducible; live search results vary by time
- DataForSEO is dramatically cheaper for SERP data
- Batch SERP fetching parallelizes cleanly
- Live search adds latency that defeats the purpose of batch pipeline

### Considered: Building a UI before running the pipeline

Rejected in favor of CLI-first development. Reasoning:
- The UI's requirements aren't known until the pipeline has run
  against real data
- CLI scripts are sufficient for single-user usage
- UI built before understanding the actual workflow optimizes for
  assumed needs, not real ones
- Pipeline phases designed as functions are reusable from any
  interface (CLI now, web UI later)

---

## Decision Criteria for Future Changes

When considering changes to the pipeline, evaluate against:

### Does this work for site #1 AND for hypothetical site #20?

If a proposed change only makes sense for the current site, it
probably belongs in that site's YAML config, not in pipeline code.

### Does this preserve phase independence?

If a change creates a dependency where Phase N can only run if
Phase N+1 has specific state, that's a regression. Each phase should
work given valid inputs from earlier phases, no matter how Phase N+1
behaves.

### Does this break multi-tenancy?

Any change that doesn't filter by site_id, doesn't pass site_id
through, or assumes a single-site context is a regression.

### Does this add complexity without clear current need?

Lazy abstraction principle. If the complexity supports current
functionality, add it. If it supports anticipated future functionality
without current need, defer.

### Does this work from a fresh database?

Any change should be testable by running the pipeline against an
empty database with appropriate config. Setup steps required for the
change to work belong in `schema/schema.sql` or documented in README.md.

---

## Open Questions

Questions that will be answered as the project evolves:

### When does the team tool actually get built?

The trigger should be measurable pain. When you find yourself:
- Onboarding a VA to use the pipeline and explaining CLI commands
- Manually running pipelines for 3+ sites concurrently
- Wishing for visibility into pipeline status without database queries

That's when the UI investment pays off. Not before.

### What's the right number of phases?

12 phases captures the current pipeline. As more sites run through it
and patterns emerge, some phases may merge (if they're always run
together) or split (if internal complexity grows). The number isn't
sacred.

### How do downstream pipelines consume topics?

Current scope ends with approved topics in `topics` table. Article
generation reads from there. The interface between this pipeline and
article generation is the `topics` and `topic_keywords` table schema.
Changes to that schema affect downstream consumers.

### When do we need source library integration?

Source library (for article generation grounding) is currently a
separate concern. If it becomes valuable to surface source counts
during clustering review (e.g., "this topic has 3 authoritative
sources available"), the schema would extend. Deferred until needed.

---

## Anti-Patterns to Avoid

Patterns observed in similar projects that create problems:

### "Just hardcode it for now"

Hardcoded values multiply over time. Each one becomes a place where
the second site won't work without editing code. Always put
niche-specific values in config.

### "We'll add tests later"

If the test coverage doesn't exist after the 8-hour MVP, it won't
exist after the 80-hour expansion either. The right approach: trust
the database state as your test (data flowing through correctly is
the success signal), defer formal tests until the team tool phase.

### "Let's build a plugin architecture"

Plugin architectures for clustering algorithms, embedding providers,
or anything else are deferred until there are at least two
implementations to compare. Building plugin systems before knowing
what varies is over-engineering.

### "We need a queue system for jobs"

For single-user CLI usage, just run jobs synchronously. Job queues
(Celery, RQ, etc.) are infrastructure to add when concurrent users
or long-running orchestration require it.

### "Let's optimize the database schema for performance"

The schema as designed prioritizes clarity and multi-tenancy. Performance
optimization (indexes, partitions, materialized views) happens after
queries become measurably slow on real data, not before.

---

## How This Document Should Be Maintained

This brief is intended to be relatively stable. Update it when:

- Core architecture changes (new principle added, existing one revised)
- Major scope decisions are made (e.g., "we're now multi-language")
- The "What This Is NOT" section needs new items
- Future contributors will benefit from documented reasoning

Don't update it for:

- Implementation details (those go in `docs/architecture.md`)
- Specific decisions on parameters or thresholds (those go in
  `docs/decisions-log.md`)
- Phase-specific behavior (those go in `docs/pipeline-phases.md`)

If you find yourself updating this brief frequently, the content
probably belongs in a more specific document.
