from functools import lru_cache

from .openai_client import LLMError, OpenAILLM

__all__ = ["OpenAILLM", "LLMError", "get_llm"]


@lru_cache
def get_llm() -> OpenAILLM:
    from app.config import get_settings

    s = get_settings()
    return OpenAILLM(
        api_key=s.openai_api_key,
        silo_model=s.openai_silo_model,
        embedding_model=s.openai_embedding_model,
    )
