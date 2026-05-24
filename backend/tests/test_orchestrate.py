import math

from app.dataforseo import DataForSEOClient
from app.pipeline.orchestrate import (
    PipelineTopic,
    cluster_preview,
    gate_and_cluster,
    run_refinement_pipeline,
)


class FakeDFS:
    """Covers both the expansion and competitor-mining surfaces."""

    # expansion endpoints
    def keyword_ideas(self, anchor, limit=0):
        return ["idea kw"]

    def keyword_suggestions(self, anchor, limit=0):
        return ["seed suggestion"]

    def query_fanouts(self, anchor, limit=0):
        return ["seed fanout"]

    def people_also_ask(self, anchor):
        return []

    def autocomplete(self, kw):
        return []

    # competitor endpoints
    def serp_top_urls(self, keyword, top_n=5):
        if keyword == "retatrutide":
            return ["https://seedcomp.com/x"]
        if "Benefits" in keyword:
            return ["https://comp.com/a"]
        return []

    def ranked_keywords(self, domain, limit=500, max_position=20):
        return {
            "comp.com": ["gated competitor kw"],
            "seedcomp.com": ["seed competitor kw"],
        }.get(domain, [])

    domain_of = staticmethod(DataForSEOClient.domain_of)


# All keywords embed to the same direction as the topic anchors -> all active.
def _embed(texts):
    return [[1.0, 0.0] for _ in texts]


def _topics():
    return [
        PipelineTopic(id="t1", name="Benefits", embedding=[1.0, 0.0], gated=True),
        PipelineTopic(id="t2", name="Access", embedding=[1.0, 0.0], gated=False),
    ]


def test_pipeline_composes_all_stages():
    r = run_refinement_pipeline(
        seed="retatrutide", topics=_topics(), dfs=FakeDFS(), embed_fn=_embed,
        relevance_threshold=0.62,
    )
    assert set(r.per_topic_gated) == {"t1", "t2"}

    def kws(tid):
        return {g.keyword for g in r.per_topic_gated[tid] if g.status == "active"}

    # Expansion lands on both topics (suggestions/fan-outs fan from the seed).
    assert {"idea kw", "seed suggestion", "seed fanout"} <= kws("t1")
    assert {"idea kw", "seed suggestion", "seed fanout"} <= kws("t2")
    # Gated topic gets its own competitor keyword; the seed's fans to both.
    assert "gated competitor kw" in kws("t1")
    assert "gated competitor kw" not in kws("t2")
    assert "seed competitor kw" in kws("t1")
    assert "seed competitor kw" in kws("t2")


def _unit(*xs):
    n = math.sqrt(sum(x * x for x in xs)) or 1.0
    return [x / n for x in xs]


def test_gate_and_cluster_threshold_sensitivity():
    # Anchor [1,0]; three keywords at descending cosine (~0.995, ~0.581, ~0.196).
    # The re-gate harness reuses this on a stored pool to tune the threshold.
    vecs = {
        "kw high": _unit(1.0, 0.1),
        "kw mid": _unit(1.0, 1.4),
        "kw low": _unit(1.0, 5.0),
    }

    def embed(texts):
        return [vecs[t] for t in texts]

    pool = {"t1": {"kw high": ["s"], "kw mid": ["s"], "kw low": ["s"]}}
    common = dict(per_topic_lists=pool, topic_names={"t1": "T1"},
                  topic_embeddings={"t1": _unit(1.0, 0.0)}, embed_fn=embed)

    strict = gate_and_cluster(**common, relevance_threshold=0.62)
    loose = gate_and_cluster(**common, relevance_threshold=0.50)

    def actives(r):
        return {g.keyword for g in r.per_topic_gated["t1"] if g.status == "active"}

    assert actives(strict) == {"kw high"}              # only the near-anchor kw
    assert actives(loose) == {"kw high", "kw mid"}     # lowering admits the mid kw
    assert loose.clustering_log["topics"]["t1"]["grouping_count"] >= 1


def test_cluster_preview_granularity_sweep():
    # alpha · beta cosine ~0.894: connected at edge 0.55 (1 grouping), split at 0.9.
    vecs = {"alpha kw": _unit(1.0, 0.0), "beta kw": _unit(1.0, 0.5)}

    def embed(texts):
        return [vecs[t] for t in texts]

    out = cluster_preview(
        per_topic_lists={"t1": {"alpha kw": ["s"], "beta kw": ["s"]}},
        topic_names={"t1": "T1"},
        topic_embeddings={"t1": _unit(1.0, 0.0)},
        embed_fn=embed,
        relevance_threshold=0.5,
        configs=[(0.55, 1.0), (0.9, 1.0)],
    )
    assert out["active_keywords"] == 2
    by_edge = {c["edge_threshold"]: c["groupings"] for c in out["configs"]}
    assert by_edge[0.55] == 1          # coarse: one grouping
    assert by_edge[0.9] == 2           # finer: edges drop, splits into two
    assert out["configs"][0]["size_buckets"]["2-4"] == 1


def test_pipeline_clusters_and_counts():
    r = run_refinement_pipeline(
        seed="retatrutide", topics=_topics(), dfs=FakeDFS(), embed_fn=_embed,
    )
    assert r.clustering_log["edge_threshold"] == 0.55
    assert set(r.clustering_log["topics"]) == {"t1", "t2"}
    # identical embeddings -> one grouping per topic
    assert r.clustering_log["topics"]["t1"]["grouping_count"] == 1
    assert r.counts()["active"] > 0
    assert r.degraded_notes == []


def test_competitor_source_tag_present_on_mined_keyword():
    r = run_refinement_pipeline(
        seed="retatrutide", topics=_topics(), dfs=FakeDFS(), embed_fn=_embed,
    )
    by_kw = {g.keyword: g for g in r.per_topic_gated["t1"]}
    assert by_kw["gated competitor kw"].sources == ["competitor"]


def test_clustering_node_cap_bounds_per_topic_input():
    # With max_nodes=1, each topic clusters at most one keyword even though the
    # gate produced several actives (the rest stay active but unclustered).
    r = run_refinement_pipeline(
        seed="retatrutide", topics=_topics(), dfs=FakeDFS(), embed_fn=_embed,
        clustering_max_nodes=1,
    )
    for tid in ("t1", "t2"):
        active = [g for g in r.per_topic_gated[tid] if g.status == "active"]
        assert len(active) > 1  # gate kept several
        log = r.clustering_log["topics"][tid]
        clustered = sum(g["size"] for g in log["groupings"])
        assert clustered == 1  # but only one fed into clustering


def test_ungated_session_still_mines_seed_only():
    topics = [PipelineTopic(id="t1", name="Benefits", embedding=[1.0, 0.0], gated=False)]
    r = run_refinement_pipeline(
        seed="retatrutide", topics=topics, dfs=FakeDFS(), embed_fn=_embed,
    )
    active = {g.keyword for g in r.per_topic_gated["t1"] if g.status == "active"}
    assert "seed competitor kw" in active          # seed always mined
    assert "gated competitor kw" not in active      # nothing gated
