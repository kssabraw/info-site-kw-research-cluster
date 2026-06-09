"""M6 site architecture tests (PRD §7.11): per-pillar editorial content via the
LLM, deterministic linking-matrix assembly, degraded fallback, and the §15.2
acceptance rules (one pillar per silo, up-links, no orphans, pillar lateral links
only above the cosine threshold)."""

import threading

from app.llm import AnthropicError
from app.pipeline.architecture import (
    ArticleInput,
    PillarInput,
    run_architecture_generation,
)
from app.pipeline.architecture.generate import (
    _lateral_article_links,
    _lateral_pillar_links,
)


class FakeArchitect:
    """Returns a preset submit_pillar payload, or raises to exercise the
    reprompt/degrade path. Thread-safe (pillars are written in parallel)."""

    def __init__(self, payload=None, raises=False):
        self.payload = payload or {
            "title": "The Complete Guide",
            "target_keyword": "guide",
            "summary": "An overview.",
            "h2_outline": ["H2 one", "H2 two"],
        }
        self.raises = raises
        self.calls = 0
        self._lock = threading.Lock()

    def call_tool(self, **kwargs):
        with self._lock:
            self.calls += 1
        if self.raises:
            raise AnthropicError("boom")
        return self.payload


def _article(aid: str, name: str, peers=None) -> ArticleInput:
    return ArticleInput(
        id=aid, name=name, primary_keyword=name, intent="informational",
        peer_article_links=peers or [],
    )


def _pillar(tid: str, name: str, articles) -> PillarInput:
    return PillarInput(
        topic_id=tid, silo_name=name, rationale="why",
        relationship_type="use_case", articles=articles,
    )


# ---- run_architecture_generation: structure & acceptance criteria ----------


def test_one_pillar_per_silo_with_uplinks_and_no_orphans():
    pillars_in = [
        _pillar("t1", "Dosage", [_article("c1", "low dose"), _article("c2", "high dose")]),
        _pillar("t2", "Safety", [_article("c3", "side effects")]),
    ]
    result = run_architecture_generation(
        seed="retatrutide",
        audience="patients",
        pillars_input=pillars_in,
        architect=FakeArchitect(),
        topic_embeddings={"t1": [1.0, 0.0], "t2": [0.0, 1.0]},  # orthogonal -> no link
        cluster_centroids={},
    )
    # #1: one pillar per accepted silo.
    assert {p.topic_id for p in result.pillars} == {"t1", "t2"}
    # Pillar links DOWN to all its supporting articles.
    by_topic = {p.topic_id: p for p in result.pillars}
    assert set(by_topic["t1"].supporting_article_ids) == {"c1", "c2"}
    assert by_topic["t2"].supporting_article_ids == ["c3"]
    # #2: every supporting article links UP to its pillar.
    assert all(a.parent_pillar_topic_id for a in result.supporting_articles)
    parents = {a.article_id: a.parent_pillar_topic_id for a in result.supporting_articles}
    assert parents == {"c1": "t1", "c2": "t1", "c3": "t2"}
    # #3: no orphans — every supporting article is in its pillar's down-links.
    for a in result.supporting_articles:
        assert a.article_id in by_topic[a.parent_pillar_topic_id].supporting_article_ids


def test_silo_without_articles_is_skipped_not_a_childless_pillar():
    pillars_in = [_pillar("t1", "Dosage", [_article("c1", "low dose")])]
    result = run_architecture_generation(
        seed="x", audience="", pillars_input=pillars_in,
        architect=FakeArchitect(), topic_embeddings={}, cluster_centroids={},
        skipped_silos=["Empty Silo"],
    )
    assert [p.topic_id for p in result.pillars] == ["t1"]
    assert result.skipped_silos == ["Empty Silo"]


def test_pillar_editorial_fields_come_from_the_llm():
    payload = {
        "title": "The Complete Guide to Triple Agonists",
        "target_keyword": "triple agonist drugs",
        "summary": "What they are.",
        # Any h2_outline the model emits is ignored — the writer owns the outline.
        "h2_outline": ["Mechanism", "Comparisons"],
    }
    result = run_architecture_generation(
        seed="x", audience="", pillars_input=[_pillar("t1", "Drugs", [_article("c1", "a")])],
        architect=FakeArchitect(payload=payload), topic_embeddings={}, cluster_centroids={},
    )
    p = result.pillars[0]
    assert p.title == "The Complete Guide to Triple Agonists"
    assert p.target_keyword == "triple agonist drugs"
    assert p.h2_outline == []  # writer module generates pillar headings at write time
    assert p.degraded is False


# ---- degraded fallback -----------------------------------------------------


def test_pillar_degrades_to_stub_when_architect_fails(monkeypatch):
    # No real backoff sleeps in the test; just assert the retry-then-degrade path.
    monkeypatch.setattr("app.pipeline.architecture.generate.time.sleep", lambda *_: None)
    arch = FakeArchitect(raises=True)
    result = run_architecture_generation(
        seed="x", audience="", pillars_input=[_pillar("t1", "Dosage", [_article("c1", "low dose")])],
        architect=arch, topic_embeddings={}, cluster_centroids={},
    )
    p = result.pillars[0]
    assert p.degraded is True
    assert p.title == "Dosage"               # stub title = silo name
    assert p.h2_outline == []                 # writer owns the outline (even on the stub)
    assert arch.calls == 3                    # all attempts exhausted before degrading
    assert result.all_degraded() is True


def test_transient_failure_backs_off_between_attempts(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("app.pipeline.architecture.generate.time.sleep", lambda s: sleeps.append(s))
    arch = FakeArchitect(raises=True)
    run_architecture_generation(
        seed="x", audience="", pillars_input=[_pillar("t1", "Dosage", [_article("c1", "a")])],
        architect=arch, topic_embeddings={}, cluster_centroids={},
    )
    # Backoff happens between attempts but not after the final one.
    assert len(sleeps) == 2
    assert all(s > 0 for s in sleeps)


def test_blank_title_triggers_reprompt_then_stub():
    # Shape failures reprompt immediately (no backoff sleep), so no monkeypatch.
    arch = FakeArchitect(payload={"title": "", "target_keyword": "", "summary": "",
                                  "h2_outline": []})
    result = run_architecture_generation(
        seed="x", audience="", pillars_input=[_pillar("t1", "Dosage", [_article("c1", "a")])],
        architect=arch, topic_embeddings={}, cluster_centroids={},
    )
    assert result.pillars[0].degraded is True
    assert arch.calls == 3


# ---- lateral pillar links (#4): cosine > threshold -------------------------


def test_lateral_pillar_links_only_above_threshold_and_symmetric():
    links = _lateral_pillar_links(
        ["t1", "t2", "t3"],
        {
            "t1": [1.0, 0.0],
            "t2": [0.99, 0.14],   # cosine to t1 ~0.99 > 0.55 -> linked
            "t3": [0.0, 1.0],     # orthogonal to t1 -> not linked
        },
        threshold=0.55,
        max_per_pillar=5,
    )
    assert links["t2"] == ["t1"]
    assert links["t1"] == ["t2"]   # symmetric (when each side has room under the cap)
    assert links["t3"] == []       # below threshold


def test_lateral_pillar_links_skip_silos_without_embeddings():
    links = _lateral_pillar_links(
        ["t1", "t2"], {"t1": [1.0, 0.0]}, threshold=0.55, max_per_pillar=5,
    )
    assert links == {"t1": [], "t2": []}


def test_lateral_pillar_links_caps_at_top_n_by_cosine():
    # Seven pillars all within the cosine threshold of t0; with max_per_pillar=5,
    # t0's outbound list keeps the FIVE closest peers (highest cosine) and drops
    # the bottom two. The owner-set "no page > 5 outbound internal links" rule
    # for pillar laterals lives here.
    # Vectors crafted so t0 -> t1..t7 cosines descend monotonically:
    #   t1 closest, t7 farthest (but still above threshold).
    pillar_ids = [f"t{i}" for i in range(8)]
    embeddings = {
        "t0": [1.0, 0.0],
        "t1": [1.00, 0.05],
        "t2": [1.00, 0.10],
        "t3": [1.00, 0.15],
        "t4": [1.00, 0.20],
        "t5": [1.00, 0.25],
        "t6": [1.00, 0.30],
        "t7": [1.00, 0.35],
    }
    links = _lateral_pillar_links(
        pillar_ids, embeddings, threshold=0.55, max_per_pillar=5,
    )
    # All seven peers exceed the cosine bar, but t0's list is capped to its
    # five closest (t1..t5). t6 and t7 are dropped from t0's outbound list.
    assert len(links["t0"]) == 5
    assert links["t0"] == ["t1", "t2", "t3", "t4", "t5"]
    # t6 and t7 still appear in the OTHER pillars' lists (their own caps allow
    # it), confirming the cap is per-pillar rather than a global edge drop.
    assert "t6" in links["t1"] or "t6" in links["t7"]


def test_lateral_pillar_links_cap_of_zero_disables_the_cap():
    # max_per_pillar=0 (or negative) returns every above-threshold peer — used
    # in code paths where the caller wants the raw graph (e.g. diagnostics).
    pillar_ids = [f"t{i}" for i in range(8)]
    embeddings = {f"t{i}": [1.0, i * 0.05] for i in range(8)}
    links = _lateral_pillar_links(
        pillar_ids, embeddings, threshold=0.55, max_per_pillar=0,
    )
    assert len(links["t0"]) == 7  # every other pillar above the threshold


# ---- lateral article links: prioritize peer links, fill by centroid --------


def test_lateral_article_links_prioritize_existing_peer_links():
    a = _article("c1", "a", peers=["c9"])  # c9 is a cross-silo dedup peer
    out = _lateral_article_links(
        a, same_silo_ids={"c1", "c2", "c3"},
        cluster_centroids={
            "c1": [1.0, 0.0], "c2": [0.9, 0.1], "c3": [0.2, 0.9],
        },
        max_links=3,
    )
    # Existing peer first, then nearest same-silo neighbors by centroid cosine.
    assert out[0] == "c9"
    assert out[1] == "c2"   # closer to c1 than c3
    assert "c1" not in out  # never links to itself
    assert len(out) <= 3


def test_lateral_article_links_capped_and_self_excluded():
    a = _article("c1", "a", peers=["c2", "c3", "c4", "c5"])
    out = _lateral_article_links(
        a, same_silo_ids={"c1"}, cluster_centroids={}, max_links=3
    )
    assert out == ["c2", "c3", "c4"]   # capped at max_links, in priority order
