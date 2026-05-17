# Database Schema

Full schema for the multi-tenant keyword discovery and clustering pipeline.
All tables include `site_id` for multi-tenancy. Schema deployed via
`schema/schema.sql`.

## Schema Overview
sites                          Root: every other table references this
├── pipeline_jobs              Job tracking per phase run
├── tangential_concepts        Phase 00 output
├── raw_keywords               All discovered keywords
│   ├── keyword_serps          SERP results per keyword
│   └── keyword_embeddings     pgvector embeddings
├── serp_urls                  URL frequency analysis (Phase 03)
├── serp_domains               Domain frequency analysis (Phase 03)
├── discovered_keywords        URL/domain mining output (Phase 04-05)
├── clusters                   Pre-review clustering output
├── topics                     Approved clusters ready for content
├── topic_keywords             Junction: keywords per topic with role
├── topic_dependencies         Junction: topic-to-topic ordering edges
└── topic_relationships        Junction: typed topic-to-topic edges

## Core Tables

### sites

Multi-tenant root. Every other table references `sites.id`. The `config`
JSONB column stores the full site YAML configuration.

```sql
CREATE TABLE sites (
    id BIGSERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    domain TEXT NOT NULL,
    display_name TEXT NOT NULL,
    niche_description TEXT,
    config JSONB NOT NULL DEFAULT '{}',
    runtime_state JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_sites_slug ON sites(slug);
CREATE INDEX idx_sites_status ON sites(status);
```

**Design notes:**
- `slug` is the human-readable identifier used in CLI commands and
  config files.
- `config` JSONB is the snapshot of the site's YAML at registration.
  Treated as **immutable** by all phases — see ADR-010.
- `runtime_state` JSONB holds operational metadata mutated by phases
  during execution (e.g., Phase 12's Google Sheet ID lives at
  `runtime_state -> 'phase_12' -> 'google_sheets_sheet_id'`). Keep
  YAML diffs clean and operational state queryable. See ADR-010.
- `niche_description` is used in Phase 00 concept mapping prompts.

### pipeline_jobs

Tracks every phase run. Used for status monitoring, cost tracking,
debugging, and reproducibility.

```sql
CREATE TABLE pipeline_jobs (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    phase TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'failed', 'skipped')),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    config_snapshot JSONB,
    output_summary JSONB,
    error_message TEXT,
    error_traceback TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, site_id)   -- ADR-018
);

CREATE INDEX idx_jobs_site_phase ON pipeline_jobs(site_id, phase);
CREATE INDEX idx_jobs_status ON pipeline_jobs(status);
CREATE INDEX idx_jobs_created ON pipeline_jobs(created_at DESC);
```

**Design notes:**
- `config_snapshot` captures the site config at the moment of run
  (enables reproducibility even if config changes later)
- `output_summary` stores stats like keyword counts, cost estimates,
  cluster counts (varies by phase)
- `phase` is a string like `'phase_01_seed_expansion'` for clarity

## Keyword Discovery Tables

### tangential_concepts

Phase 00 output. LLM-generated concept terms organized by category,
then validated for search volume.

```sql
CREATE TABLE tangential_concepts (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    concept_term TEXT NOT NULL,
    category TEXT NOT NULL,
    llm_reasoning TEXT,
    estimated_volume INTEGER,
    volume_validated_at TIMESTAMPTZ,
    promoted_to_seeds BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (site_id, concept_term)
);

CREATE INDEX idx_concepts_site ON tangential_concepts(site_id);
CREATE INDEX idx_concepts_category ON tangential_concepts(site_id, category);
CREATE INDEX idx_concepts_promoted ON tangential_concepts(site_id, promoted_to_seeds);
```

**Design notes:**
- `category` matches the concept mapping taxonomy (e.g., 'mechanism',
  'drug_class', 'competitor', etc.)
- `promoted_to_seeds` flags concepts that survived volume validation
  and are used in Phase 01 seed expansion
- Concepts below volume threshold stay in table but aren't promoted

### raw_keywords

All discovered keywords from any source. Central table for the pipeline.

```sql
CREATE TABLE raw_keywords (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    keyword_normalized TEXT NOT NULL
        CHECK (
            length(keyword_normalized) > 0
            AND keyword_normalized = lower(keyword_normalized)
            AND keyword_normalized = btrim(keyword_normalized)
            AND keyword_normalized !~ '\s\s'
        ),

    -- Discovery metadata
    discovery_method TEXT NOT NULL,
    discovery_source TEXT,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Search data
    search_volume INTEGER,
    cpc NUMERIC(10, 2),
    competition NUMERIC(3, 2),
    keyword_difficulty INTEGER,
    
    -- Classification (tier = role in topic taxonomy; orthogonal to
    -- inclusion. See ADR-007.)
    tier TEXT
        CHECK (tier IN ('primary', 'secondary', 'longtail', 'branded')),
    primary_intent TEXT,
    intent_confidence NUMERIC(3, 2),
    suggested_subfolder TEXT,
    language_register TEXT
        CHECK (language_register IN ('clinical', 'consumer', 'user_slang')),
    tangential_distance INTEGER
        CHECK (tangential_distance BETWEEN 0 AND 3),
    
    -- Filtering
    relevance_score NUMERIC(3, 2),
    is_included BOOLEAN NOT NULL DEFAULT TRUE,
    exclusion_reason TEXT,
    
    UNIQUE (site_id, keyword_normalized),
    UNIQUE (id, site_id)   -- ADR-018
);

CREATE INDEX idx_keywords_site ON raw_keywords(site_id);
CREATE INDEX idx_keywords_normalized ON raw_keywords(site_id, keyword_normalized);
CREATE INDEX idx_keywords_intent ON raw_keywords(site_id, primary_intent);
CREATE INDEX idx_keywords_volume ON raw_keywords(site_id, search_volume DESC);
CREATE INDEX idx_keywords_included ON raw_keywords(site_id, is_included);
CREATE INDEX idx_keywords_tier ON raw_keywords(site_id, tier);
```

**Design notes:**
- `keyword_normalized` is the dedup key. The canonical normalization
  rules are pinned in
  [decisions-log.md ADR-006](decisions-log.md#adr-006-keyword-normalization-rules).
  All writes must go through `pipeline/utils/normalize.py::normalize_keyword()`.
  The CHECK constraint catches obvious bypasses (uppercase, untrimmed,
  double spaces, empty) — it is a fence, not the rule.
- `discovery_method` examples: 'seed_expansion', 'paa_harvest',
  'related_search', 'url_mining', 'domain_mining', 'manual'
- `discovery_source` captures the specific source URL or domain that
  surfaced this keyword (when applicable)
- `tier` is a role in the topic taxonomy
  (primary / secondary / longtail / branded), set during Phase 06
  filtering. It is **not** an exclusion signal — for that, see
  `is_included` and ADR-007.
- `is_included = FALSE` plus `exclusion_reason` is the sole way to
  exclude a keyword from downstream phases.
- All classification fields are nullable until their respective phases run

### keyword_serps

SERP results captured for keywords. Used for clustering refinement
and competitor analysis.

```sql
CREATE TABLE keyword_serps (
    id BIGSERIAL PRIMARY KEY,
    keyword_id BIGINT NOT NULL,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position BETWEEN 1 AND 100),
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    title TEXT,
    snippet TEXT,
    serp_features JSONB,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (keyword_id, position),
    -- Tenant-scoped FK (ADR-018)
    FOREIGN KEY (keyword_id, site_id) REFERENCES raw_keywords (id, site_id) ON DELETE CASCADE
);

CREATE INDEX idx_serps_keyword ON keyword_serps(keyword_id);
CREATE INDEX idx_serps_url ON keyword_serps(url);
CREATE INDEX idx_serps_site_domain ON keyword_serps(site_id, domain);
```

**Design notes:**
- `position` 1-10 is most common, 1-20 for some mining queries
- `serp_features` stores PAA, related searches, featured snippet info as JSONB
- Denormalized `site_id` for query performance (avoid joins through keyword_id)

### keyword_embeddings

Vector embeddings for clustering. Uses pgvector extension.

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE keyword_embeddings (
    keyword_id BIGINT PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    embedding HALFVEC(3072),
    model_version TEXT NOT NULL,
    enriched_text TEXT,
    embedded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Tenant-scoped FK (ADR-018)
    FOREIGN KEY (keyword_id, site_id) REFERENCES raw_keywords (id, site_id) ON DELETE CASCADE
);

CREATE INDEX idx_embeddings_site ON keyword_embeddings(site_id);
CREATE INDEX idx_embeddings_hnsw ON keyword_embeddings
    USING hnsw (embedding halfvec_cosine_ops);
```

**Design notes:**
- Default dimensions 3072 (text-embedding-3-large native)
- Stored as `HALFVEC` (half-precision, 2 bytes per element) rather than
  `VECTOR` (4 bytes). pgvector's HNSW index supports `VECTOR` only up to
  2000 dims, `HALFVEC` up to 4000. Half-precision cosine similarity at
  3072 dims is within ~1% of full precision — well below clustering noise.
  See `docs/decisions-log.md` ADR-003.
- Can be reduced via Matryoshka (1024 or 1536) if storage matters
- `enriched_text` is the actual string that was embedded
  (keyword + intent + SERP titles), useful for debugging
- HNSW index enables fast similarity queries
- Storage: 3072 × 2 bytes = ~6 KB per row; 15K keywords → ~90 MB per site

### serp_urls

URL frequency analysis from Phase 03. Identifies authoritative URLs
in the niche.

```sql
CREATE TABLE serp_urls (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    frequency INTEGER NOT NULL,
    avg_position NUMERIC(4, 2),
    mining_priority TEXT
        CHECK (mining_priority IN ('high', 'medium', 'low', 'skip')),
    mining_depth INTEGER,
    mined_at TIMESTAMPTZ,
    mining_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (mining_status IN ('pending', 'mining', 'completed', 'failed', 'skipped')),
    UNIQUE (site_id, url)
);

CREATE INDEX idx_serp_urls_site ON serp_urls(site_id);
CREATE INDEX idx_serp_urls_frequency ON serp_urls(site_id, frequency DESC);
CREATE INDEX idx_serp_urls_priority ON serp_urls(site_id, mining_priority);
```

**Design notes:**
- `frequency` = number of seed SERPs this URL appears in
- `mining_priority` determined by frequency: high (10+), medium (5-9),
  low (3-4), skip (<3 or flagged noisy)
- `mining_depth` = max keywords to fetch from this URL (100/50/20)

### serp_domains

Domain frequency analysis from Phase 03. Used to auto-derive
competitor list for Phase 05.

```sql
CREATE TABLE serp_domains (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    frequency INTEGER NOT NULL,
    avg_position NUMERIC(4, 2),
    is_competitor BOOLEAN NOT NULL DEFAULT FALSE,
    mining_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (mining_status IN ('pending', 'mining', 'completed', 'failed', 'skipped')),
    mined_at TIMESTAMPTZ,
    UNIQUE (site_id, domain)
);

CREATE INDEX idx_serp_domains_site ON serp_domains(site_id);
CREATE INDEX idx_serp_domains_freq ON serp_domains(site_id, frequency DESC);
CREATE INDEX idx_serp_domains_competitor ON serp_domains(site_id, is_competitor);
```

**Design notes:**
- `is_competitor` set to TRUE for top N domains (where N comes from
  config: `auto_competitor_count`)
- Phase 05 mines `WHERE is_competitor = TRUE`

### discovered_keywords

Staging table for keywords from URL/domain mining (Phase 04-05) before
they're promoted to `raw_keywords`. Allows filtering before adding to
main pool.

```sql
CREATE TABLE discovered_keywords (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    source_type TEXT NOT NULL
        CHECK (source_type IN ('url_mining', 'domain_mining')),
    source_identifier TEXT NOT NULL,
    source_url_frequency INTEGER,
    url_position INTEGER,
    search_volume INTEGER,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    promoted_to_raw BOOLEAN NOT NULL DEFAULT FALSE,
    promotion_reason TEXT
);

CREATE INDEX idx_discovered_site ON discovered_keywords(site_id);
CREATE INDEX idx_discovered_keyword ON discovered_keywords(site_id, keyword);
CREATE INDEX idx_discovered_promoted ON discovered_keywords(site_id, promoted_to_raw);
```

**Design notes:**
- `source_identifier` is the URL (for url_mining) or domain (for domain_mining)
- `source_url_frequency` from `serp_urls.frequency` — higher = more
  authoritative source
- Phase 06 (filtering) decides which discovered keywords get promoted
  to `raw_keywords`

## Clustering and Topic Tables

### clusters

Pre-review clustering output. Each cluster represents a candidate topic.
Created by Phase 10 (HDBSCAN) and refined by Phase 11 (SERP overlap).

```sql
CREATE TABLE clusters (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    
    -- Cluster identity
    cluster_label TEXT,
    primary_keyword_candidate TEXT,
    intent TEXT,
    suggested_subfolder TEXT,
    
    -- Cluster stats
    member_count INTEGER NOT NULL DEFAULT 0,
    total_search_volume INTEGER,
    avg_cluster_similarity NUMERIC(3, 2),
    
    -- Confidence and review
    confidence_score NUMERIC(3, 2),
    review_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'approved', 'rejected', 'merged', 'split')),
    review_action TEXT,
    reviewed_at TIMESTAMPTZ,
    reviewer_notes TEXT,
    
    -- Relationships (set during/after review)
    merged_into_cluster_id BIGINT,
    split_from_cluster_id BIGINT,
    
    -- Metadata
    clustering_run_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Self-merge prevention (ADR-018)
    CHECK (merged_into_cluster_id IS NULL OR merged_into_cluster_id != id),
    CHECK (split_from_cluster_id IS NULL OR split_from_cluster_id != id),
    -- Composite uniqueness for tenant-scoped FKs (ADR-018)
    UNIQUE (id, site_id),
    -- Tenant-scoped FKs (ADR-018)
    FOREIGN KEY (merged_into_cluster_id, site_id) REFERENCES clusters (id, site_id),
    FOREIGN KEY (split_from_cluster_id, site_id) REFERENCES clusters (id, site_id),
    FOREIGN KEY (clustering_run_id, site_id) REFERENCES pipeline_jobs (id, site_id)
);

CREATE INDEX idx_clusters_site ON clusters(site_id);
CREATE INDEX idx_clusters_intent ON clusters(site_id, intent);
CREATE INDEX idx_clusters_status ON clusters(site_id, review_status);
CREATE INDEX idx_clusters_confidence ON clusters(site_id, confidence_score);
CREATE INDEX idx_clusters_subfolder ON clusters(site_id, suggested_subfolder);
```

**Design notes:**
- `confidence_score` is defined by a fixed formula in
  [decisions-log.md ADR-004](decisions-log.md#adr-004-define-clustersconfidence_score-as-a-weighted-sum-of-three-signals):
  `0.50 * intra_similarity + 0.30 * intent_agreement + 0.20 * serp_overlap`.
  Single-member clusters store `NULL` and are always routed to human review.
  Phase 10 is the only writer of this column; downstream code must not
  recompute it inline.
- `review_status` transitions: pending → approved/rejected, or
  pending → merged/split (which creates child clusters)
- `clustering_run_id` enables comparing different clustering runs

### cluster_members

Junction table: which keywords are in which cluster.

```sql
CREATE TABLE cluster_members (
    cluster_id BIGINT NOT NULL,
    keyword_id BIGINT NOT NULL,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    similarity_score NUMERIC(4, 3),
    is_centroid BOOLEAN NOT NULL DEFAULT FALSE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (cluster_id, keyword_id),
    -- Tenant-scoped FKs (ADR-018)
    FOREIGN KEY (cluster_id, site_id) REFERENCES clusters (id, site_id) ON DELETE CASCADE,
    FOREIGN KEY (keyword_id, site_id) REFERENCES raw_keywords (id, site_id) ON DELETE CASCADE
);

CREATE INDEX idx_cluster_members_cluster ON cluster_members(cluster_id);
CREATE INDEX idx_cluster_members_keyword ON cluster_members(keyword_id);
CREATE INDEX idx_cluster_members_site ON cluster_members(site_id);
```

**Design notes:**
- `similarity_score` = embedding similarity to cluster centroid
- `is_centroid` = the keyword closest to cluster center (good candidate
  for primary keyword)

### topics

Approved clusters become topics. Topics are what gets exported for
article generation.

```sql
CREATE TABLE topics (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    source_cluster_id BIGINT,
    
    -- Topic identity. slug and subfolder formats per ADR-008.
    primary_keyword TEXT NOT NULL,
    title TEXT,
    slug TEXT NOT NULL CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    subfolder TEXT NOT NULL CHECK (subfolder ~ '^/([a-z0-9-]+/)+$'),
    url_path TEXT GENERATED ALWAYS AS (subfolder || slug || '/') STORED,
    
    -- Classification
    intent TEXT NOT NULL,
    pillar_level TEXT NOT NULL
        CHECK (pillar_level IN ('root', 'pillar', 'sub_pillar', 'leaf')),
    tangential_distance INTEGER DEFAULT 0,
    
    -- Metadata
    description TEXT,
    target_word_count INTEGER,
    ymyl_risk TEXT
        CHECK (ymyl_risk IN ('low', 'medium', 'high')),
    regulatory_sensitivity TEXT
        CHECK (regulatory_sensitivity IN ('low', 'medium', 'high')),
    freshness_tier TEXT
        CHECK (freshness_tier IN ('evergreen', 'medium', 'high')),
    
    -- Hierarchy
    parent_topic_id BIGINT,
    -- Dependency edges live in topic_dependencies, not as a column
    -- on this table. See ADR-009.

    -- Lifecycle
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'queued', 'drafting', 'review', 'published', 'archived')),
    
    -- Stats (from cluster)
    total_search_volume INTEGER,
    keyword_count INTEGER NOT NULL DEFAULT 0,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Single UNIQUE on url_path; (site_id, slug, subfolder) is
    -- functionally identical since url_path is derived. See ADR-008.
    UNIQUE (site_id, url_path),
    UNIQUE (id, site_id),   -- ADR-018
    FOREIGN KEY (source_cluster_id, site_id) REFERENCES clusters (id, site_id),
    FOREIGN KEY (parent_topic_id, site_id) REFERENCES topics (id, site_id)
);

CREATE INDEX idx_topics_site ON topics(site_id);
CREATE INDEX idx_topics_subfolder ON topics(site_id, subfolder);
CREATE INDEX idx_topics_pillar ON topics(site_id, pillar_level);
CREATE INDEX idx_topics_status ON topics(site_id, status);
CREATE INDEX idx_topics_parent ON topics(parent_topic_id);
```

**Design notes:**
- `url_path` is generated from `subfolder` + `slug`. The CHECK
  constraints on `slug` and `subfolder` (per ADR-008) prevent
  malformed paths like `/guideshow-to/` (missing slash) or `/guides//`
  (empty slug).
- `pillar_level` determines content depth: root = homepage tier,
  pillar = major section overview, sub_pillar = topic cluster overview,
  leaf = individual article
- Dependency-ordered generation reads from `topic_dependencies`
  (see below), not from a column on this table. The previous shape
  (`depends_on_topic_ids BIGINT[]`) had no referential integrity.
- `freshness_tier` drives the refresh schedule

### topic_keywords

Junction table: which keywords belong to which topic, with their role.
This is the bridge between clustering and content generation.

```sql
CREATE TABLE topic_keywords (
    topic_id BIGINT NOT NULL,
    keyword_id BIGINT NOT NULL,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    role TEXT NOT NULL
        CHECK (role IN ('primary', 'secondary', 'supporting', 'faq')),
    suggested_heading TEXT,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (topic_id, keyword_id),
    -- Tenant-scoped FKs (ADR-018)
    FOREIGN KEY (topic_id, site_id) REFERENCES topics (id, site_id) ON DELETE CASCADE,
    FOREIGN KEY (keyword_id, site_id) REFERENCES raw_keywords (id, site_id) ON DELETE CASCADE
);

CREATE INDEX idx_topic_keywords_topic ON topic_keywords(topic_id);
CREATE INDEX idx_topic_keywords_keyword ON topic_keywords(keyword_id);
CREATE INDEX idx_topic_keywords_role ON topic_keywords(topic_id, role);
CREATE INDEX idx_topic_keywords_site ON topic_keywords(site_id);
```

**Design notes:**
- `role` mapping for content generation:
  - `primary`: the article's main target keyword (one per topic)
  - `secondary`: H2 heading candidates (2-3 per topic)
  - `supporting`: H3/subheading candidates (5-15 per topic)
  - `faq`: FAQ section question candidates (5-20 per topic)
- `suggested_heading` is optional heading text the content generator
  can use directly

### topic_dependencies

Topic-to-topic dependency edges used by the downstream article
generator to order article creation: an article that references its
prerequisites can't be drafted before they exist.

Replaces an earlier `topics.depends_on_topic_ids BIGINT[]` column;
arrays carry no referential integrity in Postgres. See ADR-009.

```sql
CREATE TABLE topic_dependencies (
    topic_id BIGINT NOT NULL,
    depends_on_topic_id BIGINT NOT NULL,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (topic_id, depends_on_topic_id),
    CHECK (topic_id != depends_on_topic_id),
    -- Tenant-scoped FKs (ADR-018)
    FOREIGN KEY (topic_id, site_id) REFERENCES topics (id, site_id) ON DELETE CASCADE,
    FOREIGN KEY (depends_on_topic_id, site_id) REFERENCES topics (id, site_id) ON DELETE RESTRICT
);

CREATE INDEX idx_topic_deps_topic ON topic_dependencies(topic_id);
CREATE INDEX idx_topic_deps_depends_on ON topic_dependencies(depends_on_topic_id);
CREATE INDEX idx_topic_deps_site ON topic_dependencies(site_id);
```

**Design notes:**
- `ON DELETE RESTRICT` on `depends_on_topic_id` is deliberate: deleting
  a topic that other topics depend on requires explicit cleanup of the
  dependency rows first. This surfaces broken graphs at delete time
  rather than letting them sit silently.
- `ON DELETE CASCADE` on `topic_id` means deleting the dependent topic
  cleans up its outgoing edges automatically.
- Self-reference is forbidden via CHECK.
- This table holds the *ordering* edge only. Other topical
  relationships (parent/child/sibling/related/comparison/glossary)
  live in `topic_relationships`.

### topic_relationships

Captures topical relationships between topics. Used for internal linking
and content planning.

```sql
CREATE TABLE topic_relationships (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    from_topic_id BIGINT NOT NULL,
    to_topic_id BIGINT NOT NULL,
    relationship_type TEXT NOT NULL
        CHECK (relationship_type IN ('parent', 'child', 'sibling', 'related', 'comparison', 'glossary_term')),
    strength NUMERIC(3, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (from_topic_id, to_topic_id, relationship_type),
    -- Symmetric relationships ('sibling', 'related', 'comparison') must
    -- be stored canonically (from_topic_id < to_topic_id) so the same
    -- undirected edge isn't recorded twice. See ADR-018.
    CHECK (
        relationship_type NOT IN ('sibling', 'related', 'comparison')
        OR from_topic_id < to_topic_id
    ),
    -- Tenant-scoped FKs (ADR-018)
    FOREIGN KEY (from_topic_id, site_id) REFERENCES topics (id, site_id) ON DELETE CASCADE,
    FOREIGN KEY (to_topic_id, site_id) REFERENCES topics (id, site_id) ON DELETE CASCADE
);

CREATE INDEX idx_topic_rels_from ON topic_relationships(from_topic_id);
CREATE INDEX idx_topic_rels_to ON topic_relationships(to_topic_id);
CREATE INDEX idx_topic_rels_site ON topic_relationships(site_id);
CREATE INDEX idx_topic_rels_type ON topic_relationships(site_id, relationship_type);
```

**Design notes:**
- Computed after topics are approved, before article generation
- `strength` based on embedding similarity of primary keywords
- Used by content generation for internal link target selection
- **Symmetric vs asymmetric:** `parent`, `child`, `glossary_term` are
  directed and may exist in either order. `sibling`, `related`,
  `comparison` are undirected and constrained to canonical
  storage (`from_topic_id < to_topic_id`) so the same edge can't
  be inserted twice. See ADR-018.

## Row Level Security

Multi-tenancy is enforced at the database layer via RLS policies.

```sql
-- Enable RLS on all multi-tenant tables
ALTER TABLE sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE tangential_concepts ENABLE ROW LEVEL SECURITY;
ALTER TABLE raw_keywords ENABLE ROW LEVEL SECURITY;
ALTER TABLE keyword_serps ENABLE ROW LEVEL SECURITY;
ALTER TABLE keyword_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE serp_urls ENABLE ROW LEVEL SECURITY;
ALTER TABLE serp_domains ENABLE ROW LEVEL SECURITY;
ALTER TABLE discovered_keywords ENABLE ROW LEVEL SECURITY;
ALTER TABLE clusters ENABLE ROW LEVEL SECURITY;
ALTER TABLE cluster_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE topics ENABLE ROW LEVEL SECURITY;
ALTER TABLE topic_keywords ENABLE ROW LEVEL SECURITY;
ALTER TABLE topic_relationships ENABLE ROW LEVEL SECURITY;

-- For single-user CLI usage: service_role bypasses RLS
-- When team UI is built: add site_users table and per-user policies
```

**Design notes:**
- RLS is enabled but no policies are defined. This is intentional for
  the current single-user CLI pipeline (service_role bypasses RLS).
- **Any non-service_role connection gets zero rows back from every
  multi-tenant table.** Not an oversight — see ADR-013.
- The trigger for adding policies is specific: the first commit that
  introduces a `site_users` table, a non-service_role connection path,
  or the team UI must also add policies in `schema/policies/` in the
  same commit. See [`schema/policies/README.md`](../schema/policies/README.md).
- Denormalized `site_id` on child tables (`keyword_serps`,
  `keyword_embeddings`, `cluster_members`, `topic_keywords`,
  `topic_dependencies`, `topic_relationships`) exists so future
  policies can filter by `site_id` directly without joining through
  the parent.

## Indexing Strategy

Indexes serve three purposes in this schema:

**1. Multi-tenancy queries**

Every common query filters by `site_id` first. Composite indexes lead
with `site_id`:

```sql
CREATE INDEX idx_keywords_intent ON raw_keywords(site_id, primary_intent);
```

**2. Pipeline lookups**

Phase queries often look up records by specific fields. These indexes
support those queries:

```sql
CREATE INDEX idx_keywords_volume ON raw_keywords(site_id, search_volume DESC);
CREATE INDEX idx_serps_url ON keyword_serps(url);
```

**3. Vector similarity**

HNSW index on embeddings for fast similarity search:

```sql
CREATE INDEX idx_embeddings_hnsw ON keyword_embeddings 
    USING hnsw (embedding vector_cosine_ops);
```

## Migration Strategy

Schema changes during development:

1. Add new tables/columns via additive migrations (don't drop)
2. Test changes against a staging Supabase project first
3. Apply to production after validation
4. Update `schema/schema.sql` to reflect current state
5. Document schema changes in `docs/decisions-log.md`

Schema changes after team UI exists:

1. Migrations become more disciplined (numbered, idempotent)
2. RLS policies update when access patterns change
3. Breaking schema changes require migration scripts for existing data

## Data Lifecycle

Typical record lifecycle from discovery to topic:

Phase 00: Concept generated → tangential_concepts
Phase 01: Concept used as seed → raw_keywords (discovery_method='seed_expansion')
Phase 02: Top keywords get SERPs → keyword_serps
Phase 03: URLs/domains analyzed → serp_urls, serp_domains
Phase 04-05: Mining produces new keywords → discovered_keywords
Phase 06: Discovered keywords filtered, promoted → raw_keywords
Phase 07: Volume enrichment → raw_keywords (updated)
Phase 08: Intent classified → raw_keywords (primary_intent set)
Phase 09: Embeddings generated → keyword_embeddings
Phase 10: Clustering → clusters, cluster_members
Phase 11: SERP refinement → clusters (updated, merged/split)
Phase 12: Review and approval → topics, topic_keywords


## Storage Estimates

Rough storage requirements per site:
sites: <1 KB
pipeline_jobs: ~1 KB per job × ~50 jobs = ~50 KB
tangential_concepts: ~200 KB (1000 concepts × 200 bytes)
raw_keywords: ~5 MB (15K keywords × ~300 bytes)
keyword_serps: ~10 MB (3K keywords × 10 results × 300 bytes)
keyword_embeddings: ~90 MB (15K × 3072 × 2 bytes, halfvec)
With 1024-dim reduction: ~30 MB
serp_urls: ~500 KB
serp_domains: ~100 KB
discovered_keywords: ~5 MB
clusters: ~500 KB
cluster_members: ~2 MB
topics: ~500 KB
topic_keywords: ~5 MB
topic_dependencies: ~200 KB
topic_relationships: ~1 MB
TOTAL per site: ~200-250 MB
20 sites: ~4-5 GB
Supabase Pro tier: 8 GB included, $0.125/GB after

Storage is not a constraint at any realistic portfolio size.
