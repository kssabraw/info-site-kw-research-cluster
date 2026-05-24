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

        try:
            body = resp.json()
        except ValueError as exc:
            # A 200 with a non-JSON body (HTML error/maintenance page, gateway
            # interstitial). Treat as a DataForSEO failure so callers can degrade.
            raise DataForSEOError(f"DataForSEO returned non-JSON for {path}") from exc
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

    # ----- M3 expansion endpoints (PRD §7.3 / §7.5) -----------------------
    @staticmethod
    def _extract_labs_keywords(task: dict) -> list[str]:
        """Pull keyword strings from a Labs result, tolerating shape variance
        (`items[].keyword` or `items[].keyword_data.keyword`)."""
        items = (task.get("result") or [{}])[0].get("items") or []
        out: list[str] = []
        for item in items:
            kw = item.get("keyword")
            if not kw and isinstance(item.get("keyword_data"), dict):
                kw = item["keyword_data"].get("keyword")
            if kw:
                out.append(kw)
        return out

    def keyword_ideas(self, anchor: str, limit: int = 1000) -> list[str]:
        task = self._post(
            "/v3/dataforseo_labs/google/keyword_ideas/live",
            [{"keywords": [anchor], "location_code": _LOCATION_CODE,
              "language_code": _LANGUAGE_CODE, "limit": limit}],
        )
        return self._extract_labs_keywords(task)

    def keyword_suggestions(self, anchor: str, limit: int = 500) -> list[str]:
        task = self._post(
            "/v3/dataforseo_labs/google/keyword_suggestions/live",
            [{"keyword": anchor, "location_code": _LOCATION_CODE,
              "language_code": _LANGUAGE_CODE, "limit": limit}],
        )
        return self._extract_labs_keywords(task)

    def query_fanouts(self, anchor: str, limit: int = 300) -> list[str]:
        # Long-tail variations via DataForSEO Labs `related_keywords`. Each item
        # carries a node keyword (keyword_data.keyword) AND a related_keywords[]
        # array of strings — harvest both (the array is the bulk of the fan-out).
        task = self._post(
            "/v3/dataforseo_labs/google/related_keywords/live",
            [{"keyword": anchor, "location_code": _LOCATION_CODE,
              "language_code": _LANGUAGE_CODE, "depth": 2, "limit": limit}],
        )
        items = (task.get("result") or [{}])[0].get("items") or []
        out: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            kd = item.get("keyword_data") or {}
            if isinstance(kd, dict) and kd.get("keyword"):
                out.append(kd["keyword"])
            for rk in item.get("related_keywords") or []:
                if rk:
                    out.append(rk)
        return out

    def people_also_ask(self, anchor: str) -> list[str]:
        """PAA questions from the SERP for `anchor` (one tier)."""
        task = self._post(
            "/v3/serp/google/organic/live/advanced",
            [{"keyword": anchor, "location_code": _LOCATION_CODE,
              "language_code": _LANGUAGE_CODE, "depth": 20,
              "people_also_ask_click_depth": 1}],
        )
        items = (task.get("result") or [{}])[0].get("items") or []
        questions: list[str] = []
        for item in items:
            if item.get("type") != "people_also_ask":
                continue
            for q in item.get("items") or []:
                title = q.get("title")
                if title:
                    questions.append(title)
        return questions

    def autocomplete(self, keyword: str) -> list[str]:
        task = self._post(
            "/v3/serp/google/autocomplete/live/advanced",
            [{"keyword": keyword, "location_code": _LOCATION_CODE,
              "language_code": _LANGUAGE_CODE}],
        )
        items = (task.get("result") or [{}])[0].get("items") or []
        out: list[str] = []
        for item in items:
            sug = item.get("suggestion") or item.get("keyword")
            if sug:
                out.append(sug)
        return out

    # ----- M4 competitor mining (PRD §7.4) --------------------------------
    def serp_top_urls(self, keyword: str, top_n: int = 5) -> list[str]:
        """Top organic result URLs (full URLs) for `keyword`, for competitor
        mining. `top_n` is 5 in standard mode, 10 in comprehensive (§7.4)."""
        task = self._post(
            "/v3/serp/google/organic/live/advanced",
            [{"keyword": keyword, "location_code": _LOCATION_CODE,
              "language_code": _LANGUAGE_CODE, "depth": max(top_n, 10)}],
        )
        items = (task.get("result") or [{}])[0].get("items") or []
        urls: list[str] = []
        for item in items:
            if item.get("type") != "organic":
                continue
            url = item.get("url")
            if url:
                urls.append(url)
            if len(urls) >= top_n:
                break
        return urls

    def ranked_keywords(
        self, target_domain: str, limit: int = 500, max_position: int = 20
    ) -> list[str]:
        """Keywords `target_domain` ranks for in organic positions 1..max_position
        (DataForSEO Labs `ranked_keywords`, PRD §7.4). The DataForSEO target is a
        domain; results are filtered to the requested rank ceiling server-side."""
        task = self._post(
            "/v3/dataforseo_labs/google/ranked_keywords/live",
            [{"target": target_domain, "location_code": _LOCATION_CODE,
              "language_code": _LANGUAGE_CODE, "limit": limit,
              "filters": [
                  ["ranked_serp_element.serp_item.rank_absolute", "<=", max_position]
              ]}],
        )
        items = (task.get("result") or [{}])[0].get("items") or []
        out: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            kd = item.get("keyword_data") or {}
            kw = kd.get("keyword") if isinstance(kd, dict) else None
            if kw:
                out.append(kw)
        return out

    @staticmethod
    def domain_of(url: str) -> str | None:
        """Bare registrable host for a URL (drops scheme, path, leading www.)."""
        host = urlparse(url).netloc.lower()
        if not host:
            return None
        if host.startswith("www."):
            host = host[4:]
        return host or None

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
