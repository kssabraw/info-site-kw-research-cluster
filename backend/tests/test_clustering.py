import math

from app.pipeline.clustering import cluster_topic, run_clustering


def _unit(*xs):
    n = math.sqrt(sum(x * x for x in xs)) or 1.0
    return [x / n for x in xs]


def test_empty_and_singleton():
    assert cluster_topic("t1", [], []) == []
    g = cluster_topic("t1", ["only"], [_unit(1, 0)])
    assert len(g) == 1
    assert g[0].keywords == ["only"]
    assert g[0].representative == "only"
    assert g[0].size == 1
    assert g[0].cohesion == 1.0


def test_two_separated_clusters():
    # Two tight pairs on orthogonal axes -> Louvain should find 2 groupings.
    keywords = ["a1", "a2", "b1", "b2"]
    embeddings = [
        _unit(1, 0.02), _unit(1, 0.0),     # cluster A (cos ~1.0, > 0.55)
        _unit(0.02, 1), _unit(0.0, 1),     # cluster B
    ]
    groupings = cluster_topic("t1", keywords, embeddings)
    assert len(groupings) == 2
    members = {tuple(sorted(g.keywords)) for g in groupings}
    assert members == {("a1", "a2"), ("b1", "b2")}
    for g in groupings:
        assert g.size == 2
        assert g.cohesion > 0.55
        assert g.representative in g.keywords
        assert g.id.startswith("t1:g")


def test_orthogonal_keywords_are_isolated_singletons():
    # Three mutually orthogonal vectors -> no edges -> three singleton groupings.
    keywords = ["x", "y", "z"]
    embeddings = [_unit(1, 0, 0), _unit(0, 1, 0), _unit(0, 0, 1)]
    groupings = cluster_topic("t1", keywords, embeddings)
    assert len(groupings) == 3
    assert all(g.size == 1 for g in groupings)


def test_grouping_ids_are_unique_and_cover_all_keywords():
    keywords = ["a1", "a2", "b1"]
    embeddings = [_unit(1, 0), _unit(1, 0.01), _unit(0, 1)]
    groupings = cluster_topic("t1", keywords, embeddings)
    ids = [g.id for g in groupings]
    assert len(ids) == len(set(ids))
    covered = {kw for g in groupings for kw in g.keywords}
    assert covered == set(keywords)


def test_run_clustering_per_topic_and_log_shape():
    res = run_clustering(
        per_topic_keywords={"t1": ["a1", "a2"], "t2": ["only"]},
        per_topic_embeddings={
            "t1": [_unit(1, 0), _unit(1, 0.01)],
            "t2": [_unit(0, 1)],
        },
    )
    assert set(res.per_topic) == {"t1", "t2"}
    log = res.to_log()
    assert log["edge_threshold"] == 0.55
    assert log["topics"]["t1"]["grouping_count"] == 1
    assert log["topics"]["t1"]["groupings"][0]["size"] == 2
    assert "keywords" in log["topics"]["t1"]["groupings"][0]


def test_determinism_same_input_same_groupings():
    keywords = ["a1", "a2", "b1", "b2"]
    embeddings = [_unit(1, 0.02), _unit(1, 0), _unit(0.02, 1), _unit(0, 1)]
    a = cluster_topic("t1", keywords, embeddings)
    b = cluster_topic("t1", keywords, embeddings)
    assert [(g.id, tuple(g.keywords)) for g in a] == [(g.id, tuple(g.keywords)) for g in b]
