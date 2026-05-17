-- ============================================================================
-- Multi-Tenant Keyword Discovery & Clustering Pipeline
-- Canonical current-state schema
-- ============================================================================
--
-- This file reflects the schema at HEAD. Use it for fresh deploys. For
-- migrating an existing database, apply schema/migrations/NNNN_*.sql in
-- order. Both files must be updated together — see
-- schema/migrations/README.md for the convention.
--
-- Idempotent: safe to re-run against a fresh or partially-deployed db
-- (uses IF NOT EXISTS / OR REPLACE / DROP IF EXISTS).
--
-- For schema documentation and design notes, see docs/database-schema.md
-- ============================================================================

\set ON_ERROR_STOP on

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
    config JSONB NOT NULL DEFAULT '{}',
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
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
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
    UNIQUE (site_id, keyword_normalized)
);

CREATE INDEX IF NOT EXISTS idx_keywords_site ON raw_keywords(site_id);
CREATE INDEX IF NOT EXISTS idx_keywords_normalized ON raw_keywords(site_id, keyword_normalized);
CREATE INDEX IF NOT EXISTS idx_keywords_intent ON raw_keywords(site_id, primary_intent);
CREATE INDEX IF NOT EXISTS idx_keywords_volume ON raw_keywords(site_id, search_volume DESC);
CREATE INDEX IF NOT EXISTS idx_keywords_included ON raw_keywords(site_id, is_included);
CREATE INDEX IF NOT EXISTS idx_keywords_tier ON raw_keywords(site_id, tier);

CREATE TABLE IF NOT EXISTS keyword_serps (
    id BIGSERIAL PRIMARY KEY,
    keyword_id BIGINT NOT NULL REFERENCES raw_keywords(id) ON DELETE CASCADE,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position BETWEEN 1 AND 100),
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    title TEXT,
    snippet TEXT,
    serp_features JSONB,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (keyword_id, position)
);

CREATE INDEX IF NOT EXISTS idx_serps_keyword ON keyword_serps(keyword_id);
CREATE INDEX IF NOT EXISTS idx_serps_site ON keyword_serps(site_id);
CREATE INDEX IF NOT EXISTS idx_serps_url ON keyword_serps(url);
CREATE INDEX IF NOT EXISTS idx_serps_domain ON keyword_serps(domain);
CREATE INDEX IF NOT EXISTS idx_serps_site_domain ON keyword_serps(site_id, domain);

-- embedding uses HALFVEC (half-precision, 2 bytes per element) because
-- pgvector's HNSW index supports up to 2000 dims on VECTOR but up to
-- 4000 dims on HALFVEC. text-embedding-3-large is 3072 dims native.
-- Precision loss vs VECTOR is well below 1% on cosine similarity at 3072 dims.
-- See docs/decisions-log.md ADR-003.
CREATE TABLE IF NOT EXISTS keyword_embeddings (
    keyword_id BIGINT PRIMARY KEY REFERENCES raw_keywords(id) ON DELETE CASCADE,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    embedding HALFVEC(3072),
    model_version TEXT NOT NULL,
    enriched_text TEXT,
    embedded_at TIMESTAMPTZ NOT NULL DEFAULT now()
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
    merged_into_cluster_id BIGINT REFERENCES clusters(id),
    split_from_cluster_id BIGINT REFERENCES clusters(id),
    clustering_run_id BIGINT REFERENCES pipeline_jobs(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_clusters_site ON clusters(site_id);
CREATE INDEX IF NOT EXISTS idx_clusters_intent ON clusters(site_id, intent);
CREATE INDEX IF NOT EXISTS idx_clusters_status ON clusters(site_id, review_status);
CREATE INDEX IF NOT EXISTS idx_clusters_confidence ON clusters(site_id, confidence_score);
CREATE INDEX IF NOT EXISTS idx_clusters_subfolder ON clusters(site_id, suggested_subfolder);

CREATE TABLE IF NOT EXISTS cluster_members (
    cluster_id BIGINT NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    keyword_id BIGINT NOT NULL REFERENCES raw_keywords(id) ON DELETE CASCADE,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    similarity_score NUMERIC(4, 3),
    is_centroid BOOLEAN NOT NULL DEFAULT FALSE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (cluster_id, keyword_id)
);

CREATE INDEX IF NOT EXISTS idx_cluster_members_cluster ON cluster_members(cluster_id);
CREATE INDEX IF NOT EXISTS idx_cluster_members_keyword ON cluster_members(keyword_id);
CREATE INDEX IF NOT EXISTS idx_cluster_members_site ON cluster_members(site_id);

CREATE TABLE IF NOT EXISTS topics (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    source_cluster_id BIGINT REFERENCES clusters(id),
    primary_keyword TEXT NOT NULL,
    title TEXT,
    slug TEXT NOT NULL,
    subfolder TEXT NOT NULL,
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
    parent_topic_id BIGINT REFERENCES topics(id),
    depends_on_topic_ids BIGINT[],
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'queued', 'drafting', 'review', 'published', 'archived')),
    total_search_volume INTEGER,
    keyword_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (site_id, url_path),
    UNIQUE (site_id, slug, subfolder)
);

CREATE INDEX IF NOT EXISTS idx_topics_site ON topics(site_id);
CREATE INDEX IF NOT EXISTS idx_topics_subfolder ON topics(site_id, subfolder);
CREATE INDEX IF NOT EXISTS idx_topics_pillar ON topics(site_id, pillar_level);
CREATE INDEX IF NOT EXISTS idx_topics_status ON topics(site_id, status);
CREATE INDEX IF NOT EXISTS idx_topics_parent ON topics(parent_topic_id);

CREATE TABLE IF NOT EXISTS topic_keywords (
    topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    keyword_id BIGINT NOT NULL REFERENCES raw_keywords(id) ON DELETE CASCADE,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('primary', 'secondary', 'supporting', 'faq')),
    suggested_heading TEXT,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (topic_id, keyword_id)
);

CREATE INDEX IF NOT EXISTS idx_topic_keywords_topic ON topic_keywords(topic_id);
CREATE INDEX IF NOT EXISTS idx_topic_keywords_keyword ON topic_keywords(keyword_id);
CREATE INDEX IF NOT EXISTS idx_topic_keywords_role ON topic_keywords(topic_id, role);
CREATE INDEX IF NOT EXISTS idx_topic_keywords_site ON topic_keywords(site_id);

CREATE TABLE IF NOT EXISTS topic_relationships (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    from_topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    to_topic_id BIGINT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL
        CHECK (relationship_type IN ('parent', 'child', 'sibling', 'related', 'comparison', 'glossary_term')),
    strength NUMERIC(3, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (from_topic_id, to_topic_id, relationship_type)
);

CREATE INDEX IF NOT EXISTS idx_topic_rels_from ON topic_relationships(from_topic_id);
CREATE INDEX IF NOT EXISTS idx_topic_rels_to ON topic_relationships(to_topic_id);
CREATE INDEX IF NOT EXISTS idx_topic_rels_site ON topic_relationships(site_id);
CREATE INDEX IF NOT EXISTS idx_topic_rels_type ON topic_relationships(site_id, relationship_type);

-- ============================================================================
-- Row Level Security
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

-- ============================================================================
-- Schema deployment complete
-- ============================================================================
