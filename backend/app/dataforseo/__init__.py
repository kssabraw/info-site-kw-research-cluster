from functools import lru_cache

from .client import DataForSEOClient, DataForSEOError

__all__ = ["DataForSEOClient", "DataForSEOError", "get_dataforseo"]


@lru_cache
def get_dataforseo() -> DataForSEOClient:
    from app.config import get_settings

    s = get_settings()
    return DataForSEOClient(
        base_url=s.dataforseo_base_url,
        login=s.dataforseo_login,
        password=s.dataforseo_password,
    )
