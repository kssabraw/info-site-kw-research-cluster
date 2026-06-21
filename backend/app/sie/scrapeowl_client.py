"""SIE Module 4: page scraping via ScrapeOwl (new service, key provisioned
2026-06-15). JS rendering on; retries; per-page scrape_status + failure reason.

Follows the DataForSEO client shape: structured external_call log (§16.3), cost
metered via `record_cost` (estimate until first invoices), cooperative
cancellation between scrapes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ScrapeResult:
    url: str
    html: str | None
    text: str | None
    markdown: str | None
    scrape_status: str           # "success" | "failed"
    failure_reason: str | None = None


class ScrapeOwlError(Exception):
    pass


# PRD M4 failure reasons, mapped from HTTP/transport conditions.
def _failure_reason(status: int | None, exc: Exception | None) -> str:
    import httpx

    if isinstance(exc, httpx.TimeoutException):
        return "Timeout"
    if isinstance(exc, httpx.HTTPError):
        return "Scrape API error"
    if status in (403, 401):
        return "Blocked by robots or firewall"
    if status and status >= 400:
        return "HTTP error"
    return "Scrape API error"


class ScrapeOwlClient:
    def __init__(
        self, api_key: str, base_url: str, *, cost_per_scrape: float = 0.0008,
        timeout_s: float = 60.0, max_attempts: int = 3,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._cost = cost_per_scrape
        self._timeout = timeout_s
        self._max_attempts = max(1, max_attempts)

    def scrape(self, url: str) -> ScrapeResult:
        """Scrape one URL (JS-rendered). Never raises for a single page — returns a
        failed ScrapeResult so the pipeline degrades per-page (PRD M4)."""
        import httpx  # lazy: keeps ScrapeResult importable without httpx

        from app.cancellation import raise_if_cancelled
        from app.cost_meter import record_cost

        raise_if_cancelled()
        payload = {
            "api_key": self._api_key, "url": url, "render_js": True, "html": True,
        }
        started = time.perf_counter()
        last_status: int | None = None
        last_exc: Exception | None = None
        for attempt in range(self._max_attempts):
            try:
                resp = httpx.post(
                    f"{self._base_url}/scrape", json=payload, timeout=self._timeout
                )
                last_status = resp.status_code
                if resp.status_code >= 400:
                    last_exc = None
                    continue
                body = resp.json()
                record_cost(self._cost)
                self._log(url, resp.status_code, started, "success")
                html = body.get("html") or body.get("data")
                if not html:
                    return ScrapeResult(url, None, None, None, "failed", "Empty page")
                return ScrapeResult(
                    url=url, html=html, text=body.get("text"),
                    markdown=body.get("markdown"), scrape_status="success",
                )
            except (httpx.HTTPError, ValueError) as exc:
                last_exc = exc
        self._log(url, last_status, started, "failed")
        return ScrapeResult(
            url, None, None, None, "failed", _failure_reason(last_status, last_exc)
        )

    def _log(self, url: str, status: int | None, started: float, outcome: str) -> None:
        logger.info(
            "external_call",
            extra={
                "event": "external_call", "service": "scrapeowl", "endpoint": "/scrape",
                "url": url, "status": status, "outcome": outcome,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "cost_usd": self._cost if outcome == "success" else 0.0,
            },
        )
