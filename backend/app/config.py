from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service configuration, sourced from environment variables.

    On Railway most of these are inherited from the AR Tools project-level env
    (PRD §14.2). Service-specific values have sensible defaults so the service
    boots in any environment.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_anon_key: str = ""

    # The Postgres schema all this app's tables live under (PRD §14.3).
    fanout_schema: str = "fanout"

    # OpenAI — silo discovery (GPT-5.4 w/ browsing) + embeddings (PRD §14.2).
    openai_api_key: str = ""
    openai_silo_model: str = "gpt-5.4"
    openai_embedding_model: str = "text-embedding-3-small"

    # DataForSEO — demand sample + SERP structure during silo discovery.
    dataforseo_login: str = ""
    dataforseo_password: str = ""
    dataforseo_base_url: str = "https://api.dataforseo.com"

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
