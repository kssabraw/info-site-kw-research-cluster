import time

from app.dataforseo import DataForSEOClient, DataForSEOError
from app.pipeline.expansion import ExpansionTopic, build_anchor, run_expansion


def test_build_anchor_seed_qualifies():
    # Seed already in the name -> unchanged.
    assert build_anchor("retatrutide", "how retatrutide works") == "how retatrutide works"
    # Generic silo name -> seed prepended.
    assert build_anchor("retatrutide", "weight loss use") == "retatrutide weight loss use"
    # Case-insensitive containment.
    assert build_anchor("Mercury", "mercury toxicity") == "mercury toxicity"


def test_query_fanouts_harvests_related_keyword_arrays(monkeypatch):
    c = DataForSEOClient(base_url="http://x", login="l", password="p")
    fake_task = {
        "result": [
            {
                "items": [
                    {"keyword_data": {"keyword": "node1"}, "related_keywords": ["r1", "r2"]},
                    {"keyword_data": {"keyword": "node2"}, "related_keywords": ["r3"]},
                ]
            }
        ]
    }
    monkeypatch.setattr(c, "_post", lambda path, payload: fake_task)
    out = c.query_fanouts("anchor")
    assert set(out) == {"node1", "r1", "r2", "node2", "r3"}


class FakeDFS:
    def __init__(
        self,
        *,
        ideas=None,
        suggestions=None,
        fanouts=None,
        paa=None,
        autocomplete_map=None,
        fail=(),
        autocomplete_fail=(),
    ):
        self.ideas = ideas or []
        self.suggestions = suggestions or []
        self.fanouts = fanouts or []
        self.paa = paa or {}
        self.autocomplete_map = autocomplete_map or {}
        self.fail = set(fail)
        self.autocomplete_fail = set(autocomplete_fail)

    def keyword_ideas(self, anchor, limit=0):
        if "keyword_ideas" in self.fail:
            raise DataForSEOError("boom")
        return list(self.ideas)

    def keyword_suggestions(self, anchor, limit=0):
        if "keyword_suggestions" in self.fail:
            raise DataForSEOError("boom")
        return list(self.suggestions)

    def query_fanouts(self, anchor, limit=0):
        if "query_fanouts" in self.fail:
            raise DataForSEOError("boom")
        return list(self.fanouts)

    def people_also_ask(self, anchor):
        if "paa" in self.fail:
            raise DataForSEOError("boom")
        return list(self.paa.get(anchor, []))

    def autocomplete(self, keyword):
        if keyword in self.autocomplete_fail:
            raise DataForSEOError("boom")
        return list(self.autocomplete_map.get(keyword, []))


def _run(dfs, **kw):
    return run_expansion(topics=[ExpansionTopic(id="t1", anchor="seed")], dfs=dfs, **kw)


def test_aggregates_and_dedupes_sources_case_insensitively():
    dfs = FakeDFS(ideas=["A", "b"], suggestions=["B", "c"], fanouts=["d"])
    r = _run(dfs)
    kws = r.per_topic["t1"]
    assert set(kws) == {"a", "b", "c", "d"}
    # "b" came from ideas and suggestions (B normalizes to b) -> merged sources
    assert kws["b"] == ["keyword_ideas", "keyword_suggestions"]
    assert kws["d"] == ["query_fanouts"]
    assert r.degraded_notes == []


def test_paa_two_tier_and_cap():
    dfs = FakeDFS(
        paa={
            "seed": ["q1", "q2", "q3"],
            "q1": ["t1a", "t1b"],
            "q2": ["t2a"],
            "q3": ["t3a"],
        }
    )
    r = _run(dfs, paa_tier1_seeds=2, paa_tier2_cap=2)
    kws = r.per_topic["t1"]
    assert kws["q1"] == ["paa_t1"]
    assert kws["q3"] == ["paa_t1"]
    # tier-2 capped at 2 -> only the first two from q1
    tier2 = {k for k, src in kws.items() if "paa_t2" in src}
    assert tier2 == {"t1a", "t1b"}
    assert "t2a" not in kws


def test_endpoint_failure_degrades_not_blocks():
    dfs = FakeDFS(ideas=["a"], suggestions=["b"], fail=("keyword_ideas",))
    r = _run(dfs)
    assert "b" in r.per_topic["t1"]  # other sources still present
    assert any("keyword_ideas unavailable" in n for n in r.degraded_notes)


class _ValueErrorIdeasDFS(FakeDFS):
    def keyword_ideas(self, anchor, limit=0):
        raise ValueError("malformed result shape")  # NOT a DataForSEOError


def test_non_dataforseo_error_degrades_not_crashes():
    # A parsing/JSON error (e.g. a 200 with an HTML body) must degrade the
    # source, not abort the whole run.
    dfs = _ValueErrorIdeasDFS(suggestions=["b"])
    r = _run(dfs)
    assert "b" in r.per_topic["t1"]
    assert any("keyword_ideas unavailable" in n for n in r.degraded_notes)


def test_autocomplete_merges_suggestions():
    dfs = FakeDFS(ideas=["a"], autocomplete_map={"a": ["a x", "a y"]})
    r = _run(dfs)
    kws = r.per_topic["t1"]
    assert kws["a x"] == ["autocomplete"]
    assert kws["a y"] == ["autocomplete"]


class _SlowDFS:
    def _sleep(self):
        time.sleep(0.2)

    def keyword_ideas(self, a, limit=0):
        self._sleep()
        return ["a"]

    def keyword_suggestions(self, a, limit=0):
        self._sleep()
        return ["b"]

    def query_fanouts(self, a, limit=0):
        self._sleep()
        return []

    def people_also_ask(self, a):
        self._sleep()
        return []

    def autocomplete(self, kw):
        self._sleep()
        return []


def test_time_budget_caps_the_run():
    # A tiny budget against slow endpoints must stop and flag, not hang.
    started = time.monotonic()
    r = run_expansion(
        topics=[ExpansionTopic(id="t1", anchor="seed")],
        dfs=_SlowDFS(),
        max_workers=1,
        time_budget_s=0.1,
    )
    assert time.monotonic() - started < 5.0  # returned promptly, didn't hang
    assert any("stopped at the time limit" in n for n in r.degraded_notes)


def test_autocomplete_skipped_when_majority_fail():
    dfs = FakeDFS(ideas=["a", "b"], autocomplete_fail=("a", "b"))
    r = _run(dfs)
    kws = r.per_topic["t1"]
    assert not any("autocomplete" in src for src in kws.values())
    assert any("Autocomplete enrichment unavailable" in n for n in r.degraded_notes)
