-- ============================================================================
-- Migration 0001: initial schema
-- ============================================================================
-- Why: First-time deployment of the multi-tenant keyword discovery and
-- clustering pipeline. Creates 14 tables, pgvector extension, RLS
-- enablement, and updated_at triggers.
--
-- Embeddings use HALFVEC(3072) rather than VECTOR(3072) so HNSW indexes
-- work — pgvector HNSW caps VECTOR at 2000 dims, HALFVEC at 4000.
-- See docs/decisions-log.md ADR-003.
-- ============================================================================

\set ON_ERROR_STOP on
BEGIN;

-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- Core: sites and job tracking
-- ============================================================================

CREATE TABLE IF NOT EXISTS sites (
    id BIGSERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    domain TEXT NOT NULL,
    display_name TEXT NOT NULL,
    niche_description TEXT,
    -- config: immutable input from YAML, snapshotted at site registration
    config JSONB NOT NULL DEFAULT '{}',
    -- runtime_state: mutable, written by phases for operational metadata
    -- (sheet IDs, run counters, derived caches). See ADR-010 — keeps
    -- YAML diffs noise-free and clarifies what's reproducible from
    -- pipeline_jobs.config_snapshot alone (config) vs needs runtime_state too.
    runtime_state JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sites_slug ON sites(slug);
CREATE INDEX IF NOT EXISTS idx_sites_status ON sites(status);

CREATE TABLE IF NOT EXISTS pipeline_jobs (
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
    -- Composite uniqueness for tenant-scoped FKs (ADR-018).
    UNIQUE (id, site_id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_site_phase ON pipeline_jobs(site_id, phase);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON pipeline_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON pipeline_jobs(created_at DESC);

-- ============================================================================
-- Keyword Discovery
-- ============================================================================

CREATE TABLE IF NOT EXISTS tangential_concepts (
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

CREATE INDEX IF NOT EXISTS idx_concepts_site ON tangential_concepts(site_id);
CREATE INDEX IF NOT EXISTS idx_concepts_category ON tangential_concepts(site_id, category);
CREATE INDEX IF NOT EXISTS idx_concepts_promoted ON tangential_concepts(site_id, promoted_to_seeds);

CREATE TABLE IF NOT EXISTS raw_keywords (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    -- keyword_normalized must come from pipeline/utils/normalize.py
    -- per docs/decisions-log.md ADR-006. The CHECK below catches the
    -- cheapest bypass mistakes (uppercase, untrimmed, double spaces,
    -- empty) but is NOT a substitute for the canonical normalizer.
    keyword_normalized TEXT NOT NULL
        CHECK (
            length(keyword_normalized) > 0
            AND keyword_normalized = lower(keyword_normalized)
            AND keyword_normalized = btrim(keyword_normalized)
            AND keyword_normalized !~ '\s\s'
        ),
    discovery_method TEXT NOT NULL,
    discovery_source TEXT,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    search_volume INTEGER,
    cpc NUMERIC(10, 2),
    competition NUMERIC(3, 2),
    keyword_difficulty INTEGER,
    -- tier = role in the topic taxonomy; orthogonal to inclusion.
    -- For exclusion, set is_included = FALSE and exclusion_reason. See ADR-007.
    tier TEXT CHECK (tier IN ('primary', 'secondary', 'longtail', 'branded')),
    primary_intent TEXT,
    intent_confidence NUMERIC(3, 2),
    suggested_subfolder TEXT,
    language_register TEXT CHECK (language_register IN ('clinical', 'consumer', 'user_slang')),
    tangential_distance INTEGER CHECK (tangential_distance BETWEEN 0 AND 3),
    relevance_score NUMERIC(3, 2),
    is_included BOOLEAN NOT NULL DEFAULT TRUE,
    exclusion_reason TEXT,
    UNIQUE (site_id, keyword_normalized),
    -- Composite uniqueness for tenant-scoped FKs (ADR-018).
    UNIQUE (id, site_id)
);

CREATE INDEX IF NOT EXISTS idx_keywords_site ON raw_keywords(site_id);
CREATE INDEX IF NOT EXISTS idx_keywords_normalized ON raw_keywords(site_id, keyword_normalized);
CREATE INDEX IF NOT EXISTS idx_keywords_intent ON raw_keywords(site_id, primary_intent);
CREATE INDEX IF NOT EXISTS idx_keywords_volume ON raw_keywords(site_id, search_volume DESC);
CREATE INDEX IF NOT EXISTS idx_keywords_included ON raw_keywords(site_id, is_included);
CREATE INDEX IF NOT EXISTS idx_keywords_tier ON raw_keywords(site_id, tier);

CREATE TABLE IF NOT EXISTS keyword_serps (
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
    -- Tenant-scoped FK: prevents cross-site keyword reference. ADR-018.
    FOREIGN KEY (keyword_id, site_id) REFERENCES raw_keywords (id, site_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_serps_keyword ON keyword_serps(keyword_id);
CREATE INDEX IF NOT EXISTS idx_serps_url ON keyword_serps(url);
-- idx_serps_site_domain covers (site_id) and (site_id, domain) queries;
-- standalone idx_serps_site and idx_serps_domain are redundant. The
-- architecture defers cross-site domain queries, so dropping them
-- saves write cost without removing query support. Cleanup tier.
CREATE INDEX IF NOT EXISTS idx_serps_site_domain ON keyword_serps(site_id, domain);

-- embedding uses HALFVEC (half-precision, 2 bytes per element) because
-- pgvector's HNSW index supports up to 2000 dims on VECTOR but up to
-- 4000 dims on HALFVEC. text-embedding-3-large is 3072 dims native.
-- Precision loss vs VECTOR is well below 1% on cosine similarity at 3072 dims.
-- See docs/decisions-log.md ADR-003.
CREATE TABLE IF NOT EXISTS keyword_embeddings (
    keyword_id BIGINT PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    embedding HALFVEC(3072),
    model_version TEXT NOT NULL,
    enriched_text TEXT,
    embedded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Tenant-scoped FK: prevents cross-site keyword reference. ADR-018.
    FOREIGN KEY (keyword_id, site_id) REFERENCES raw_keywords (id, site_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_embeddings_site ON keyword_embeddings(site_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_hnsw ON keyword_embeddings
    USING hnsw (embedding halfvec_cosine_ops);

CREATE TABLE IF NOT EXISTS serp_urls (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    frequency INTEGER NOT NULL,
    avg_position NUMERIC(4, 2),
    mining_priority TEXT CHECK (mining_priority IN ('high', 'medium', 'low', 'skip')),
    mining_depth INTEGER,
    mined_at TIMESTAMPTZ,
    mining_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (mining_status IN ('pending', 'mining', 'completed', 'failed', 'skipped')),
    UNIQUE (site_id, url)
);

CREATE INDEX IF NOT EXISTS idx_serp_urls_site ON serp_urls(site_id);
CREATE INDEX IF NOT EXISTS idx_serp_urls_frequency ON serp_urls(site_id, frequency DESC);
CREATE INDEX IF NOT EXISTS idx_serp_urls_priority ON serp_urls(site_id, mining_priority);

CREATE TABLE IF NOT EXISTS serp_domains (
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

CREATE INDEX IF NOT EXISTS idx_serp_domains_site ON serp_domains(site_id);
CREATE INDEX IF NOT EXISTS idx_serp_domains_freq ON serp_domains(site_id, frequency DESC);
CREATE INDEX IF NOT EXISTS idx_serp_domains_competitor ON serp_domains(site_id, is_competitor);

CREATE TABLE IF NOT EXISTS discovered_keywords (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('url_mining', 'domain_mining')),
    source_identifier TEXT NOT NULL,
    source_url_frequency INTEGER,
    url_position INTEGER,
    search_volume INTEGER,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    promoted_to_raw BOOLEAN NOT NULL DEFAULT FALSE,
    promotion_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_discovered_site ON discovered_keywords(site_id);
CREATE INDEX IF NOT EXISTS idx_discovered_keyword ON discovered_keywords(site_id, keyword);
CREATE INDEX IF NOT EXISTS idx_discovered_promoted ON discovered_keywords(site_id, promoted_to_raw);

-- ============================================================================
-- Clustering and Topics
-- ============================================================================

CREATE TABLE IF NOT EXISTS clusters (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    cluster_label TEXT,
    primary_keyword_candidate TEXT,
    intent TEXT,
    suggested_subfolder TEXT,
    member_count INTEGER NOT NULL DEFAULT 0,
    total_search_volume INTEGER,
    avg_cluster_similarity NUMERIC(3, 2),
    confidence_score NUMERIC(3, 2),
    review_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'approved', 'rejected', 'merged', 'split')),
    review_action TEXT,
    reviewed_at TIMESTAMPTZ,
    reviewer_notes TEXT,
    merged_into_cluster_id BIGINT,
    split_from_cluster_id BIGINT,
    clustering_run_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Self-merge prevention (ADR-018).
    CHECK (merged_into_cluster_id IS NULL OR merged_into_cluster_id != id),
    CHECK (split_from_cluster_id IS NULL OR split_from_cluster_id != id),
    -- Composite uniqueness for tenant-scoped FKs (ADR-018).
    UNIQUE (id, site_id),
    -- Tenant-scoped FKs: merges, splits, and run linkage stay in-site.
    FOREIGN KEY (merged_into_cluster_id, site_id) REFERENCES clusters (id, site_id),
    FOREIGN KEY (split_from_cluster_id, site_id) REFERENCES clusters (id, site_id),
    FOREIGN KEY (clustering_run_id, site_id) REFERENCES pipeline_jobs (id, site_id)
);

CREATE INDEX IF NOT EXISTS idx_clusters_site ON clusters(site_id);
CREATE INDEX IF NOT EXISTS idx_clusters_intent ON clusters(site_id, intent);
CREATE INDEX IF NOT EXISTS idx_clusters_status ON clusters(site_id, review_status);
CREATE INDEX IF NOT EXISTS idx_clusters_confidence ON clusters(site_id, confidence_score);
CREATE INDEX IF NOT EXISTS idx_clusters_subfolder ON clusters(site_id, suggested_subfolder);

CREATE TABLE IF NOT EXISTS cluster_members (
    cluster_id BIGINT NOT NULL,
    keyword_id BIGINT NOT NULL,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    similarity_score NUMERIC(4, 3),
    is_centroid BOOLEAN NOT NULL DEFAULT FALSE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (cluster_id, keyword_id),
    -- Tenant-scoped FKs (ADR-018).
    FOREIGN KEY (cluster_id, site_id) REFERENCES clusters (id, site_id) ON DELETE CASCADE,
    FOREIGN KEY (keyword_id, site_id) REFERENCES raw_keywords (id, site_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cluster_members_cluster ON cluster_members(cluster_id);
CREATE INDEX IF NOT EXISTS idx_cluster_members_keyword ON cluster_members(keyword_id);
CREATE INDEX IF NOT EXISTS idx_cluster_members_site ON cluster_members(site_id);

CREATE TABLE IF NOT EXISTS topics (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    source_cluster_id BIGINT,
    primary_keyword TEXT NOT NULL,
    title TEXT,
    -- slug and subfolder formats per ADR-008: kebab-case lowercase,
    -- subfolder starts and ends with '/'.
    slug TEXT NOT NULL CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    subfolder TEXT NOT NULL CHECK (subfolder ~ '^/([a-z0-9-]+/)+$'),
    url_path TEXT GENERATED ALWAYS AS (subfolder || slug || '/') STORED,
    intent TEXT NOT NULL,
    pillar_level TEXT NOT NULL
        CHECK (pillar_level IN ('root', 'pillar', 'sub_pillar', 'leaf')),
    tangential_distance INTEGER DEFAULT 0,
    description TEXT,
    target_word_count INTEGER,
    ymyl_risk TEXT CHECK (ymyl_risk IN ('low', 'medium', 'high')),
    regulatory_sensitivity TEXT CHECK (regulatory_sensitivity IN ('low', 'medium', 'high')),
    freshness_tier TEXT CHECK (freshness_tier IN ('evergreen', 'medium', 'high')),
    parent_topic_id BIGINT,
    -- topic-to-topic dependency edges live in topic_dependencies; see ADR-009
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'queued', 'drafting', 'review', 'published', 'archived')),
    total_search_volume INTEGER,
    keyword_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Single UNIQUE on url_path; (site_id, slug, subfolder) is
    -- functionally identical since url_path is derived. See ADR-008.
    UNIQUE (site_id, url_path),
    -- Composite uniqueness for tenant-scoped FKs (ADR-018).
    UNIQUE (id, site_id),
    -- Tenant-scoped FKs (ADR-018).
    FOREIGN KEY (source_cluster_id, site_id) REFERENCES clusters (id, site_id),
    FOREIGN KEY (parent_topic_id, site_id) REFERENCES topics (id, site_id)
);

CREATE INDEX IF NOT EXISTS idx_topics_site ON topics(site_id);
CREATE INDEX IF NOT EXISTS idx_topics_subfolder ON topics(site_id, subfolder);
CREATE INDEX IF NOT EXISTS idx_topics_pillar ON topics(site_id, pillar_level);
CREATE INDEX IF NOT EXISTS idx_topics_status ON topics(site_id, status);
CREATE INDEX IF NOT EXISTS idx_topics_parent ON topics(parent_topic_id);

CREATE TABLE IF NOT EXISTS topic_keywords (
    topic_id BIGINT NOT NULL,
    keyword_id BIGINT NOT NULL,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('primary', 'secondary', 'supporting', 'faq')),
    suggested_heading TEXT,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (topic_id, keyword_id),
    -- Tenant-scoped FKs (ADR-018).
    FOREIGN KEY (topic_id, site_id) REFERENCES topics (id, site_id) ON DELETE CASCADE,
    FOREIGN KEY (keyword_id, site_id) REFERENCES raw_keywords (id, site_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_topic_keywords_topic ON topic_keywords(topic_id);
CREATE INDEX IF NOT EXISTS idx_topic_keywords_keyword ON topic_keywords(keyword_id);
CREATE INDEX IF NOT EXISTS idx_topic_keywords_role ON topic_keywords(topic_id, role);
CREATE INDEX IF NOT EXISTS idx_topic_keywords_site ON topic_keywords(site_id);

-- Topic-to-topic dependency edges. Replaces the prior
-- topics.depends_on_topic_ids BIGINT[] which had no referential
-- integrity. See ADR-009.
CREATE TABLE IF NOT EXISTS topic_dependencies (
    topic_id BIGINT NOT NULL,
    depends_on_topic_id BIGINT NOT NULL,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (topic_id, depends_on_topic_id),
    CHECK (topic_id != depends_on_topic_id),
    -- Tenant-scoped FKs (ADR-018). RESTRICT on depends_on side preserves
    -- the dependency-graph integrity rule from ADR-009.
    FOREIGN KEY (topic_id, site_id) REFERENCES topics (id, site_id) ON DELETE CASCADE,
    FOREIGN KEY (depends_on_topic_id, site_id) REFERENCES topics (id, site_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_topic_deps_topic ON topic_dependencies(topic_id);
CREATE INDEX IF NOT EXISTS idx_topic_deps_depends_on ON topic_dependencies(depends_on_topic_id);
CREATE INDEX IF NOT EXISTS idx_topic_deps_site ON topic_dependencies(site_id);

CREATE TABLE IF NOT EXISTS topic_relationships (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    from_topic_id BIGINT NOT NULL,
    to_topic_id BIGINT NOT NULL,
    relationship_type TEXT NOT NULL
        CHECK (relationship_type IN ('parent', 'child', 'sibling', 'related', 'comparison', 'glossary_term')),
    strength NUMERIC(3, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (from_topic_id, to_topic_id, relationship_type),
    -- Canonicalize symmetric edges: for 'sibling', 'related', and
    -- 'comparison' the edge is undirected, so the pair must be stored
    -- with from_topic_id < to_topic_id. This prevents accidental
    -- duplicate edges like (A,B,'related') AND (B,A,'related'). Asymmetric
    -- edges ('parent', 'child', 'glossary_term') retain direction and
    -- are unconstrained by this CHECK.
    CHECK (
        relationship_type NOT IN ('sibling', 'related', 'comparison')
        OR from_topic_id < to_topic_id
    ),
    -- Tenant-scoped FKs (ADR-018).
    FOREIGN KEY (from_topic_id, site_id) REFERENCES topics (id, site_id) ON DELETE CASCADE,
    FOREIGN KEY (to_topic_id, site_id) REFERENCES topics (id, site_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_topic_rels_from ON topic_relationships(from_topic_id);
CREATE INDEX IF NOT EXISTS idx_topic_rels_to ON topic_relationships(to_topic_id);
CREATE INDEX IF NOT EXISTS idx_topic_rels_site ON topic_relationships(site_id);
CREATE INDEX IF NOT EXISTS idx_topic_rels_type ON topic_relationships(site_id, relationship_type);

-- ============================================================================
-- Row Level Security
-- ============================================================================
--
-- RLS is enabled on every multi-tenant table. No policies are defined.
--
-- Posture: service_role connections (used by the CLI pipeline) bypass RLS
-- entirely. ANY OTHER CONNECTION GETS ZERO ROWS. This is intentional for
-- the current single-user pipeline.
--
-- Policies must be added the first time any of the following lands:
--   - a site_users table mapping users to sites
--   - a code path connecting with a non-service_role key
--   - a team UI entry point
--
-- See docs/decisions-log.md ADR-013 for the full contract and
-- schema/policies/README.md for where the policy SQL will live.
-- ============================================================================

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
ALTER TABLE topic_dependencies ENABLE ROW LEVEL SECURITY;
ALTER TABLE topic_relationships ENABLE ROW LEVEL SECURITY;

-- Note: No policies defined initially. Service role bypasses RLS for
-- CLI pipeline usage. Add policies when team UI is built.

-- ============================================================================
-- Update Triggers
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_sites_updated_at ON sites;
CREATE TRIGGER update_sites_updated_at
    BEFORE UPDATE ON sites
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_topics_updated_at ON topics;
CREATE TRIGGER update_topics_updated_at
    BEFORE UPDATE ON topics
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMIT;

-- ============================================================================
-- Migration 0001 complete
-- ============================================================================
