from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service configuration, sourced from environment variables.

    On Railway most of these are inherited from the AR Tools project-level env
    (PRD §14.2). Service-specific values have sensible defaults so the service
    boots in any environment.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase. The service-role and anon keys accept the AR Tools project-level
    # names (SUPABASE_SERVICE_KEY / SUPABASE_KEY) as aliases so the service works
    # with the inherited env without renaming shared variables.
    supabase_url: str = ""
    supabase_service_role_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY"
        ),
    )
    supabase_anon_key: str = Field(
        default="",
        validation_alias=AliasChoices("SUPABASE_ANON_KEY", "SUPABASE_KEY"),
    )

    # The Postgres schema all this app's tables live under (PRD §14.3).
    fanout_schema: str = "fanout"

    # OpenAI — silo discovery (GPT-5.4 w/ browsing) + embeddings (PRD §14.2).
    openai_api_key: str = ""
    openai_silo_model: str = "gpt-5.4"
    openai_embedding_model: str = "text-embedding-3-small"
    # Responses API browsing tool type. Configurable so the exact name can be
    # corrected without a code change if OpenAI's differs (e.g. web_search_preview).
    openai_web_search_tool: str = "web_search"
    # Disambiguation gate (PRD §7.1.2 / Q16). The LLM's ambiguity signal is
    # corroborated by embedding separation between candidate interpretations:
    # ambiguity is confirmed only if the two most-distinct interpretations have a
    # cosine distance >= this threshold. Tunable during MVP testing.
    ambiguity_separation_threshold: float = 0.5

    # Anthropic — article planning orchestrator (Claude Opus 4.7, tool-use /
    # strict-schema JSON; PRD §7.10, §14.2). Reuses the AR Tools ANTHROPIC_API_KEY.
    anthropic_api_key: str = ""
    orchestrator_model: str = "claude-opus-4-7"
    orchestrator_max_tokens: int = 16000
    orchestrator_timeout_s: int = 120         # PRD §16.2: >120s -> retry once then degrade
    # The orchestrator runs per silo, but a silo with many groupings overruns a
    # single call (huge prompt + output -> timeout/truncation). Plan in chunks of
    # this many groupings, run in parallel, so each call stays small and fast.
    orchestrator_groupings_per_call: int = 12
    orchestrator_max_workers: int = 2         # parallel orchestrator calls (M6
    # architect lesson: 5 burst Anthropic's concurrent-connection 429s and the
    # chunks degraded to passthrough; 2 + the client's transport backoff holds)

    # M5 article planning (PRD §7.10).
    candidate_serp_top_n: int = 10            # top organic URLs per candidate primary
    candidate_serp_max_workers: int = 8
    candidate_serp_time_budget_s: int = 120
    # Cross-topic dedup thresholds (§7.10.4).
    dedup_primary_cosine_threshold: float = 0.85
    dedup_serp_overlap_min: float = 2 / 3     # top-3 SERP overlap fraction

    # Salience split (PRD §7.10 granularity): after planning, an over-large article
    # is sub-clustered by keyword-embedding similarity (Louvain at a higher
    # resolution) and split into multiple articles when it cleanly divides. Runs
    # automatically in the plan job. Embedding-based (no extra DataForSEO spend);
    # only articles above the keyword threshold are touched, and tiny sub-clusters
    # fold back into the largest so the long-tail isn't shattered into thin stubs.
    split_oversized_articles: bool = True
    split_min_keywords: int = 40              # only articles larger than this split
    split_resolution: float = 1.2             # > base -> finer sub-communities
    split_edge_threshold: float = 0.55        # cosine edge for the sub-graph
    # No floor on sub-article size: every sub-community becomes its own article,
    # even a 1-keyword stub. Owner-accepted maximal granularity (stub explosion is
    # acceptable; raise this knob if a future seed needs stub-suppression).
    split_min_subarticle_size: int = 1

    # Peer-entity-aware article grouping (owner-requested). After planning, any
    # keyword that names a known peer entity (from grounding's `peer_entities`) is
    # pulled into an article dedicated to that peer's relationship with the seed.
    # All "X vs Y" / "switching from X to Y" / "X alternative to Y" variants for
    # the same peer end up in one article; single-keyword peer matches still spawn
    # their own primary (no minimum — the peer-name signal is deterministic).
    peer_entity_grouping: bool = True
    # Below this many keywords, a peer-comparison bucket folds into one
    # "retatrutide vs competitors" roundup instead of shipping as a thin
    # single-keyword stub (a lone `cagrisema vs retatrutide`). 1 disables the
    # fold (every competitor its own article). 2 folds only 1-keyword stubs.
    peer_min_keywords: int = 2

    # Orphan promotion: after all planning passes finish, every active keyword
    # that the orchestrator silently omitted (singletons, redundant long-tail,
    # cross-topic-dedup loser-side losses) becomes its own singleton article.
    # Owner-requested after seeing "what is retatrutide" land in the active pool
    # but in no cluster. Zero LLM / embedding cost.
    promote_orphan_keywords: bool = True
    # Quality floor for orphan promotion: cosine score (vs. silo anchor) below
    # which silently-omitted keywords stay as orphans rather than becoming their
    # own thin article. Tightens the editorial bar without touching the gate's
    # `relevance_threshold` (which gates the pool used for clustering).
    # Empirically: 0.65 keeps the strong + foundational orphans, drops the
    # marginal long-tail (cf. retatrutide validation, 2026-05-28).
    orphan_promotion_min_score: float = 0.65

    # Enriched silo anchor (routing-calibration follow-up). At finalize, the LLM
    # generates ~N example keywords per accepted silo; their embeddings are
    # centroided with the rationale embedding to form a more discriminative anchor
    # (the rationale embedding alone is seed-dominated -> all silo anchors cluster,
    # M5 noted ~71% routing accuracy). Owner-requested. One-off LLM cost at
    # finalize (~$0.05 per session); routing at gate time stays pure-embedding.
    enriched_silo_anchor: bool = True
    silo_anchor_example_count: int = 30
    silo_anchor_max_workers: int = 5

    # LLM routing for ambiguous keywords (second-pass calibration). After the
    # gate's cosine Lever-3 picks a best silo, keywords whose top-1 vs top-2
    # silo-anchor cosine margin is below `llm_routing_margin_threshold` are
    # re-routed in batches by an LLM call. Catches the genuinely ambiguous
    # cases (where embeddings can't decide) without per-keyword LLM cost on the
    # easy ones. ~$0.40-1 per run when ~half the pool is ambiguous.
    llm_routing_enabled: bool = True
    llm_routing_margin_threshold: float = 0.04
    llm_routing_batch_size: int = 50
    llm_routing_max_workers: int = 4

    # DataForSEO — demand sample + SERP structure during silo discovery.
    dataforseo_login: str = ""
    dataforseo_password: str = ""
    dataforseo_base_url: str = "https://api.dataforseo.com"

    # M3 expansion knobs (PRD §7.3 / §7.5).
    keyword_ideas_limit: int = 1000
    keyword_suggestions_limit: int = 500
    query_fanouts_limit: int = 300
    paa_tier1_seeds: int = 8          # tier-1 questions used as tier-2 seeds
    paa_tier2_cap: int = 40           # max tier-2 questions per silo (PRD §7.3)
    autocomplete_max: int = 500       # safety cap on autocomplete calls per run
                                      # (autocomplete is the noisiest/slowest source;
                                      #  most of it gets filtered by the relevance gate)
    expansion_max_workers: int = 8    # parallel endpoint/silo workers
    expansion_time_budget_s: int = 240  # hard cap on a single expansion run (4 min)

    # M4 competitor mining (PRD §7.4).
    competitor_top_n_standard: int = 5       # top organic URLs mined per silo
    competitor_top_n_comprehensive: int = 10
    ranked_keywords_limit: int = 500         # ranked keywords pulled per domain
    competitor_max_position: int = 20        # organic rank ceiling (1..N)
    competitor_max_workers: int = 8
    competitor_time_budget_s: int = 240

    # M4 relevance gate (PRD §7.6) + clustering (§7.9).
    # 0.65 is an aggressive cutoff (owner decision) — keeps only clearly on-topic
    # keywords, roughly halving the active pool vs the prior 0.52. Re-tune via env
    # (RELEVANCE_THRESHOLD) or a per-run /regate without redeploying.
    relevance_threshold: float = 0.65        # cosine cutoff vs parent topic embedding
    # Lever 3: assign each keyword to its single best silo (argmax cosine to the
    # silo anchor) instead of keeping it active in every silo it passes in. Kills
    # the cross-silo duplication that dedup otherwise has to clean up.
    relevance_assign_best_silo: bool = True
    relevance_embed_batch: int = 1000        # keywords per embedding request
    clustering_edge_threshold: float = 0.55  # min cosine for a graph edge
    # Louvain resolution: >1 favors more, smaller communities (finer granularity).
    clustering_resolution: float = 1.0
    # Cap on keywords clustered per topic. The similarity graph is O(n^2), so
    # bound n to keep memory in check; the top-N most-relevant actives are
    # clustered, the long-tail remainder stays active but unclustered.
    clustering_max_nodes: int = 2500
    # Hard cap on active keywords per silo, applied AFTER the relevance gate
    # scores everything. The top-N most-relevant keywords per silo stay 'active'
    # and feed clustering / the Table View; the rest are demoted to
    # 'filtered_relevance'. Directly bounds article count and dedup work — sits
    # below clustering_max_nodes so a tightening of this cap visibly shrinks the
    # active pool, not just what reaches the similarity graph.
    active_per_silo_cap: int = 1000

    # §7.8 keyword metrics enrichment (DataForSEO Labs keyword_overview): per-
    # keyword search volume / CPC / KD / competition. Run against the active
    # pool after the gate + cap, so cost scales with active_per_silo_cap × silos
    # (~$0.40 for a typical 5-silo run at list price). Tunable per session via
    # CreateSessionBody.enrich_with_metrics; this is the workspace default.
    enrich_with_metrics_default: bool = True
    metrics_batch_size: int = 500            # keywords per keyword_overview call
    metrics_max_workers: int = 4             # parallel keyword_overview calls
    metrics_time_budget_s: int = 120

    # Recursive Fanout (PRD §7.7, Phase 1). RF deepens each silo by re-expanding
    # its top cluster representatives as sub-anchors. Mining at this level is off
    # (M5 finding: mining adds noise the gate rejects).
    fanout_subanchors_per_silo: int = 6      # top-N cluster reps re-expanded per silo
    fanout_subanchor_max_workers: int = 8
    # RF expands N silos x fanout_subanchors_per_silo anchors in one run, so a flat
    # budget that suits a base /expand (a handful of silos) starves a wide fan-out
    # and truncates its tail. Scale the budget by the sub-anchor count instead:
    # max(floor, per_anchor x count), capped. RF runs in the background worker, so
    # the cap can exceed Railway's 5-min edge limit (that only bounds the request).
    fanout_time_budget_per_anchor_s: float = 25.0
    fanout_time_budget_floor_s: float = 60.0
    fanout_time_budget_cap_s: int = 900
    # Cost surfaced to the owner before an RF run (§7.7: 5x-8x the base run).
    fanout_cost_multiplier_low: float = 5.0
    fanout_cost_multiplier_high: float = 8.0

    # M6 site architecture (PRD §7.11). Reuses the orchestrator's Anthropic client
    # (§7.11: "share the same LLM client and credentials"); one editorial call per
    # pillar, run in parallel. The linking matrix is assembled deterministically.
    # Kept low: live validation showed ~5 simultaneous pillar calls burst Anthropic
    # rate limits and degraded most pillars to stubs; 2-at-a-time + per-call backoff
    # cleared it (pillars are few, so throughput isn't the constraint).
    architect_max_workers: int = 2
    # Pillars link laterally only above this topic-embedding cosine (§15.2 #4).
    architecture_pillar_lateral_cosine: float = 0.55
    # Lateral peer links per supporting article (§7.11 "2-3 lateral links").
    architecture_lateral_article_links_max: int = 3

    # M8 VA mode (PRD §10.2 / §15.2 §7.2 #3). A VA may deep-mine at most the seed
    # + this many additional silos; the seed is always mined and never counts.
    va_deep_mine_max_silos: int = 2

    # Display-time within-cluster keyword dedup (Cluster View / PRD §9.2). After
    # surface-form normalization collapses obvious variants (plurals, articles,
    # "what is/are X", aliases like msp <-> managed service provider), the
    # remaining canonicals get a cosine pass over the per-keyword embeddings
    # persisted by the relevance gate. Pairs at or above this threshold collapse
    # to the higher-volume / higher-relevance winner. Set to 1.0 to disable the
    # cosine half without touching surface-form dedup; lower the value to
    # collapse more semantic dupes ("definition" vs "meaning") at the cost of a
    # few legitimate variants. Pure display-time pass; no DB writes.
    cluster_display_dedupe_cosine_threshold: float = 0.95

    # M10 CSV export (PRD §12). Downloads are served via a time-limited signed URL
    # the backend mints from the private csv-snapshots bucket; this is its TTL.
    # Re-issued fresh on every download, so a short window is fine.
    csv_signed_url_ttl_s: int = 3600

    # Observability (PRD §16.3)
    log_level: str = "INFO"
    # Cost attribution (PRD §16.4): the background jobs flush the running actual
    # cost to sessions.actual_cost_usd + cost_breakdown on this cadence, so the
    # live cost banner (§8.4) updates while the pipeline runs.
    cost_flush_interval_s: float = 10.0

    # CORS — comma-separated list of allowed frontend origins. "*" allows all.
    cors_allow_origins: str = "*"

    @property
    def cors_origins_list(self) -> list[str]:
        raw = self.cors_allow_origins.strip()
        if raw == "*" or raw == "":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
