from functools import lru_cache

from .anthropic_client import AnthropicError, AnthropicLLM
from .openai_client import LLMError, OpenAILLM

__all__ = [
    "OpenAILLM",
    "LLMError",
    "AnthropicLLM",
    "AnthropicError",
    "get_llm",
    "get_orchestrator",
]


@lru_cache
def get_llm() -> OpenAILLM:
    from app.config import get_settings

    s = get_settings()
    return OpenAILLM(
        api_key=s.openai_api_key,
        silo_model=s.openai_silo_model,
        embedding_model=s.openai_embedding_model,
        web_search_tool=s.openai_web_search_tool,
    )


@lru_cache
def get_orchestrator() -> AnthropicLLM:
    from app.config import get_settings

    s = get_settings()
    return AnthropicLLM(
        api_key=s.anthropic_api_key,
        model=s.orchestrator_model,
        max_tokens=s.orchestrator_max_tokens,
        timeout_s=s.orchestrator_timeout_s,
    )
