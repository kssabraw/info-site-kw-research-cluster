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
    orchestrator_max_workers: int = 5         # parallel orchestrator calls

    # M5 article planning (PRD §7.10).
    candidate_serp_top_n: int = 10            # top organic URLs per candidate primary
    candidate_serp_max_workers: int = 8
    candidate_serp_time_budget_s: int = 120
    # Cross-topic dedup thresholds (§7.10.4).
    dedup_primary_cosine_threshold: float = 0.85
    dedup_serp_overlap_min: float = 2 / 3     # top-3 SERP overlap fraction

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
    relevance_threshold: float = 0.52        # cosine cutoff vs parent topic embedding
    relevance_embed_batch: int = 1000        # keywords per embedding request
    clustering_edge_threshold: float = 0.55  # min cosine for a graph edge
    # Louvain resolution: >1 favors more, smaller communities (finer granularity).
    clustering_resolution: float = 1.0
    # Cap on keywords clustered per topic. The similarity graph is O(n^2), so
    # bound n to keep memory in check; the top-N most-relevant actives are
    # clustered, the long-tail remainder stays active but unclustered.
    clustering_max_nodes: int = 2500

    # Observability (PRD §16.3)
    log_level: str = "INFO"

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
