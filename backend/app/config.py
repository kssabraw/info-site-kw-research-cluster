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
    autocomplete_max: int = 1500      # safety cap on autocomplete calls per run
    expansion_max_workers: int = 8    # parallel endpoint/silo workers
    expansion_time_budget_s: int = 240  # hard cap on a single expansion run (4 min)

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
