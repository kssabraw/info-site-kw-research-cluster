from app.dataforseo import DataForSEOError
from app.pipeline.recursive_fanout import (
    RECURSIVE_SOURCE,
    count_sub_anchors,
    derive_sub_anchors,
    merge_into_pool,
    run_recursive_expansion,
)


def _log(per_topic_groupings: dict[str, list[dict]]) -> dict:
    """Build a statistical_clustering_log with the given per-topic groupings."""
    return {
        "topics": {
            tid: {"grouping_count": len(gs), "groupings": gs}
            for tid, gs in per_topic_groupings.items()
        }
    }


# ---- derive_sub_anchors ----------------------------------------------------


def test_derive_sub_anchors_picks_top_by_size_skips_singletons():
    log = _log({
        "t1": [
            {"id": "t1:g0", "representative": "big", "size": 9, "keywords": ["big", "x"]},
            {"id": "t1:g1", "representative": "mid", "size": 4, "keywords": ["mid", "y"]},
            {"id": "t1:g2", "representative": "small", "size": 2, "keywords": ["small", "z"]},
            {"id": "t1:g3", "representative": "lonely", "size": 1, "keywords": ["lonely"]},
        ],
    })
    out = derive_sub_anchors(clustering_log=log, topic_ids=["t1"], per_silo=2)
    # Top-2 multi-keyword reps by size; singleton excluded.
    assert out["t1"] == ["big", "mid"]


def test_derive_sub_anchors_dedupes_and_handles_empty():
    log = _log({
        "t1": [
            {"id": "t1:g0", "representative": "dup", "size": 5},
            {"id": "t1:g1", "representative": "Dup", "size": 4},  # case-dupe
            {"id": "t1:g2", "representative": "other", "size": 3},
        ],
        "t2": [
            {"id": "t2:g0", "representative": "solo", "size": 1},  # only a singleton
        ],
    })
    out = derive_sub_anchors(clustering_log=log, topic_ids=["t1", "t2", "t3"], per_silo=6)
    assert out["t1"] == ["dup", "other"]   # case-duplicate collapsed
    assert out["t2"] == []                  # no multi-keyword groupings
    assert out["t3"] == []                  # topic absent from the log
    assert count_sub_anchors(out) == 2


# ---- run_recursive_expansion -----------------------------------------------


class RecorderDFS:
    """Records which anchors each endpoint saw; returns a fixed payload."""

    def __init__(self):
        self.ideas_anchors: list[str] = []
        self.paa_anchors: list[str] = []
        self.suggestions_calls = 0
        self.fanouts_calls = 0

    def keyword_ideas(self, anchor, limit=0):
        self.ideas_anchors.append(anchor)
        return [f"{anchor} idea"]

    def keyword_suggestions(self, anchor, limit=0):
        self.suggestions_calls += 1
        return ["should-not-appear"]

    def query_fanouts(self, anchor, limit=0):
        self.fanouts_calls += 1
        return ["should-not-appear"]

    def people_also_ask(self, anchor):
        self.paa_anchors.append(anchor)
        return []

    def autocomplete(self, keyword):
        return []


def test_recursive_expansion_remaps_to_parent_and_tags_recursive():
    dfs = RecorderDFS()
    out, degraded, timed_out = run_recursive_expansion(
        seed="retatrutide",
        sub_anchors={"t1": ["dosage", "side effects"], "t2": ["cost"]},
        dfs=dfs,
    )
    # Keywords land under the real parent silo ids, never the synthetic sub-ids.
    assert set(out) == {"t1", "t2"}
    assert "::sub::" not in "".join(k for kws in out.values() for k in kws)
    # Each keyword carries the recursive provenance tag alongside its source.
    kw = "retatrutide dosage idea"
    assert kw in out["t1"]
    assert RECURSIVE_SOURCE in out["t1"][kw]
    assert "keyword_ideas" in out["t1"][kw]
    assert degraded == []
    assert timed_out is False


def test_recursive_expansion_runs_per_sub_anchor_and_skips_seed_level():
    dfs = RecorderDFS()
    run_recursive_expansion(
        seed="retatrutide",
        sub_anchors={"t1": ["dosage", "side effects"]},
        dfs=dfs,
    )
    # keyword_ideas + PAA ran once per sub-anchor (seed-qualified).
    assert sorted(dfs.ideas_anchors) == ["retatrutide dosage", "retatrutide side effects"]
    assert sorted(dfs.paa_anchors) == ["retatrutide dosage", "retatrutide side effects"]
    # Seed-level phrase-match endpoints are NOT re-run (they ran in pass 1).
    assert dfs.suggestions_calls == 0
    assert dfs.fanouts_calls == 0


def test_recursive_expansion_no_sub_anchors_is_a_noop():
    dfs = RecorderDFS()
    out, degraded, timed_out = run_recursive_expansion(
        seed="x", sub_anchors={"t1": [], "t2": []}, dfs=dfs,
    )
    assert out == {"t1": {}, "t2": {}}
    assert dfs.ideas_anchors == []
    assert degraded == [] and timed_out is False


class _FailingIdeasDFS(RecorderDFS):
    def keyword_ideas(self, anchor, limit=0):
        raise DataForSEOError("boom")


def test_recursive_expansion_degrades_on_source_failure():
    # A failing endpoint degrades that sub-anchor's source, not the whole run.
    out, degraded, _ = run_recursive_expansion(
        seed="seed", sub_anchors={"t1": ["a"]}, dfs=_FailingIdeasDFS(),
    )
    assert "t1" in out
    assert any("keyword_ideas unavailable" in n for n in degraded)


# ---- merge_into_pool -------------------------------------------------------


def test_merge_into_pool_unions_keywords_and_sources():
    base = {"t1": {"shared": ["keyword_ideas"], "base only": ["paa_t1"]}}
    add = {
        "t1": {"shared": ["recursive", "keyword_ideas"], "new": ["recursive"]},
        "t2": {"fresh": ["recursive"]},
    }
    merged = merge_into_pool(base, add)
    assert merged["t1"]["shared"] == ["keyword_ideas", "recursive"]  # sorted union
    assert merged["t1"]["base only"] == ["paa_t1"]
    assert merged["t1"]["new"] == ["recursive"]
    assert merged["t2"] == {"fresh": ["recursive"]}
