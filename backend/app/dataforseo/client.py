"""DataForSEO client — the slices needed for silo discovery (PRD §7.1.1).

M2 uses two endpoints:
- Labs `keyword_ideas` for the ~200-row demand sample on the bare seed.
- SERP `organic` to read the top domains' URL path patterns.

Failures raise DataForSEOError; the silo-discovery orchestrator decides whether
that degrades the run (demand/competitor signal optional) or halts it.
"""

import logging
import time
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# PRD scopes out location/language inputs; default to US English.
_LOCATION_CODE = 2840
_LANGUAGE_CODE = "en"


class DataForSEOError(Exception):
    pass


class DataForSEOClient:
    def __init__(self, base_url: str, login: str, password: str):
        self._base_url = base_url.rstrip("/")
        self._auth = (login, password)

    def _post(self, path: str, payload: list[dict]) -> dict:
        url = f"{self._base_url}{path}"
        started = time.perf_counter()
        try:
            resp = httpx.post(url, json=payload, auth=self._auth, timeout=60.0)
        except httpx.HTTPError as exc:
            raise DataForSEOError(f"DataForSEO request failed: {exc}") from exc
        latency_ms = round((time.perf_counter() - started) * 1000, 2)

        if resp.status_code >= 400:
            raise DataForSEOError(f"DataForSEO {resp.status_code} for {path}")

        body = resp.json()
        task = (body.get("tasks") or [{}])[0]
        logger.info(
            "external_call",
            extra={
                "event": "external_call",
                "service": "dataforseo",
                "endpoint": path,
                "latency_ms": latency_ms,
                "cost_usd": task.get("cost"),
            },
        )
        if task.get("status_code", 0) >= 40000:
            raise DataForSEOError(
                f"DataForSEO task error {task.get('status_code')}: {task.get('status_message')}"
            )
        return task

    def keyword_ideas_sample(self, seed: str, limit: int = 200) -> list[str]:
        """~200 demand-sample keywords for the bare seed (no expansion)."""
        task = self._post(
            "/v3/dataforseo_labs/google/keyword_ideas/live",
            [
                {
                    "keywords": [seed],
                    "location_code": _LOCATION_CODE,
                    "language_code": _LANGUAGE_CODE,
                    "limit": limit,
                }
            ],
        )
        items = (task.get("result") or [{}])[0].get("items") or []
        keywords: list[str] = []
        for item in items:
            kw = item.get("keyword")
            if kw:
                keywords.append(kw)
        return keywords

    def serp_competitor_paths(self, seed: str, top_n: int = 5) -> list[str]:
        """URL path patterns from the top organic domains for the seed."""
        task = self._post(
            "/v3/serp/google/organic/live/advanced",
            [
                {
                    "keyword": seed,
                    "location_code": _LOCATION_CODE,
                    "language_code": _LANGUAGE_CODE,
                    "depth": max(top_n, 10),
                }
            ],
        )
        items = (task.get("result") or [{}])[0].get("items") or []
        paths: list[str] = []
        for item in items:
            if item.get("type") != "organic":
                continue
            url = item.get("url")
            if not url:
                continue
            path = urlparse(url).path.strip("/")
            if path:
                paths.append(path)
            if len(paths) >= top_n:
                break
        return paths
