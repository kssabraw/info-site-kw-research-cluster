"""§7.8 keyword metrics enrichment: pipeline module + DataForSEO client wrapper.

No live API access. Stubs `dfs.keyword_overview` to exercise the
batching / degrade / timeout paths, and pokes the client's response parser
directly to lock the field mapping (search_volume / cpc / keyword_difficulty /
competition_index) so a DataForSEO shape change is caught loudly."""

from __future__ import annotations

import threading
import time

import pytest

from app.dataforseo.client import DataForSEOClient
from app.pipeline.metrics import enrich_keywords


class _FakeDFS:
    """Records what's asked for; returns a metrics dict per batch."""

    def __init__(self, response_by_keyword: dict[str, dict], fail_on=None, sleep_s=0.0):
        self._response = response_by_keyword
        self._fail_on = fail_on or set()  # keywords whose batch should raise
        self._sleep_s = sleep_s
        self.calls: list[list[str]] = []
        self._lock = threading.Lock()

    def keyword_overview(self, keywords: list[str]) -> dict[str, dict]:
        with self._lock:
            self.calls.append(list(keywords))
        if self._sleep_s:
            time.sleep(self._sleep_s)
        if any(k in self._fail_on for k in keywords):
            raise RuntimeError("simulated batch failure")
        return {k: v for k, v in self._response.items() if k in keywords}


# ---------------------------------------------------------------------------
# enrich_keywords
# ---------------------------------------------------------------------------
def _metrics(volume, cpc, kd=10.0, ci=0.5):
    return {
        "volume": volume,
        "cpc_usd": cpc,
        "keyword_difficulty": kd,
        "competition_index": ci,
    }


def test_enrich_keywords_batches_and_collects():
    """Unique keywords get split into batches of `batch_size`; results merge."""
    response = {f"kw{i}": _metrics(i * 10, i * 0.5) for i in range(7)}
    dfs = _FakeDFS(response)
    r = enrich_keywords(
        keywords=list(response.keys()), dfs=dfs, batch_size=3, max_workers=2
    )
    assert r.requested == 7
    assert r.enriched == 7
    assert r.metrics["kw3"]["volume"] == 30
    # 7 unique kw / batch_size 3 -> 3 batches (3, 3, 1).
    sizes = sorted(len(b) for b in dfs.calls)
    assert sizes == [1, 3, 3]
    assert not r.degraded_notes
    assert not r.timed_out


def test_enrich_keywords_dedupes_input():
    """Duplicates collapse before batching — we don't pay twice for the same kw."""
    dfs = _FakeDFS({"alpha": _metrics(100, 1.0), "beta": _metrics(200, 2.0)})
    r = enrich_keywords(
        keywords=["alpha", "beta", "alpha", "beta", "alpha"],
        dfs=dfs, batch_size=10, max_workers=1,
    )
    assert r.requested == 2
    assert r.enriched == 2
    assert sum(len(b) for b in dfs.calls) == 2


def test_enrich_keywords_degrades_failed_batch_only():
    """A batch that raises is logged + skipped; surviving batches still land."""
    response = {f"kw{i}": _metrics(i, i) for i in range(4)}
    dfs = _FakeDFS(response, fail_on={"kw0"})
    r = enrich_keywords(
        keywords=list(response.keys()), dfs=dfs, batch_size=2, max_workers=2
    )
    assert r.enriched == 2  # the surviving batch (kw2 + kw3) landed
    assert "kw0" not in r.metrics and "kw1" not in r.metrics
    assert r.metrics["kw2"]["cpc_usd"] == 2
    assert len(r.degraded_notes) == 1 and "batch of 2" in r.degraded_notes[0]


def test_enrich_keywords_empty_input_noop():
    dfs = _FakeDFS({})
    r = enrich_keywords(keywords=[], dfs=dfs, batch_size=10)
    assert r.requested == 0 and r.enriched == 0 and dfs.calls == []


def test_enrich_keywords_handles_timeout():
    """Hitting the time budget surfaces as `timed_out=True` with partial results."""
    response = {f"kw{i}": _metrics(i, i) for i in range(8)}
    # Each batch sleeps 1.0s; with 4 batches and 1 worker, we'll definitely miss
    # the 0.5s budget. (Slow tests are awkward — keeping this small.)
    dfs = _FakeDFS(response, sleep_s=1.0)
    r = enrich_keywords(
        keywords=list(response.keys()), dfs=dfs, batch_size=2,
        max_workers=1, time_budget_s=0.5,
    )
    assert r.timed_out is True
    # Anything that did complete is preserved; the rest is silently dropped.
    assert r.enriched <= 2


# ---------------------------------------------------------------------------
# DataForSEOClient.keyword_overview response shape
# ---------------------------------------------------------------------------
class _StubClient(DataForSEOClient):
    """Patches `_post` to return a canned task envelope, so we can assert the
    parser maps DataForSEO field names -> our row dict correctly. A shape
    change at DataForSEO would surface here (and a missing field shouldn't
    drop the whole row — only the field becomes None)."""

    def __init__(self, task_payload: dict):
        super().__init__("http://nope", "user", "pass")
        self._task = task_payload

    def _post(self, path, payload):  # type: ignore[override]
        return self._task


def test_keyword_overview_maps_dataforseo_fields():
    task = {
        "result": [{
            "items": [
                {
                    "keyword": "alpha",
                    "keyword_info": {
                        "search_volume": 1200, "cpc": 1.23,
                        "competition_index": 0.42,
                    },
                    "keyword_properties": {"keyword_difficulty": 38.5},
                },
                {
                    # Partial row: KD missing -> stays None, the row still lands.
                    "keyword": "beta",
                    "keyword_info": {"search_volume": 50, "cpc": None,
                                     "competition_index": 0.1},
                },
                # Garbage entries shouldn't crash the parser.
                {"not": "a keyword"},
                None,
            ]
        }]
    }
    out = _StubClient(task).keyword_overview(["alpha", "beta"])
    assert set(out) == {"alpha", "beta"}
    assert out["alpha"] == {
        "volume": 1200, "cpc_usd": 1.23,
        "competition_index": 0.42, "keyword_difficulty": 38.5,
        "search_intent": None,
    }
    assert out["beta"]["volume"] == 50
    assert out["beta"]["cpc_usd"] is None
    assert out["beta"]["keyword_difficulty"] is None


def test_keyword_overview_empty_input_skips_call():
    """Empty input shouldn't issue an HTTP request at all (would waste $)."""
    called = False

    class C(DataForSEOClient):
        def _post(self, path, payload):  # type: ignore[override]
            nonlocal called
            called = True
            return {}

    out = C("http://nope", "u", "p").keyword_overview([])
    assert out == {} and called is False


def test_keyword_overview_tolerates_empty_task():
    """A no-items task envelope returns {} without raising."""
    out = _StubClient({"result": [{"items": []}]}).keyword_overview(["x"])
    assert out == {}


@pytest.mark.parametrize("bad_value", ["", "—", "n/a"])
def test_keyword_overview_coerces_non_numeric(bad_value):
    """Non-numeric strings in numeric fields become None (don't crash parse)."""
    task = {"result": [{"items": [{
        "keyword": "alpha",
        "keyword_info": {"search_volume": bad_value, "cpc": bad_value,
                         "competition_index": bad_value},
    }]}]}
    out = _StubClient(task).keyword_overview(["alpha"])
    assert out["alpha"] == {
        "volume": None, "cpc_usd": None,
        "competition_index": None, "keyword_difficulty": None,
        "search_intent": None,
    }
