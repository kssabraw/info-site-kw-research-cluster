import math

from app.pipeline.relevance import GatedKeyword, run_relevance_gate


def _unit(*xs):
    n = math.sqrt(sum(x * x for x in xs)) or 1.0
    return [x / n for x in xs]


# A deterministic embed_fn: map known keywords to fixed 2-D vectors.
def make_embed_fn(vectors: dict[str, list[float]]):
    calls = {"n": 0}

    def embed(texts):
        calls["n"] += 1
        return [vectors[t] for t in texts]

    embed.calls = calls
    return embed


def test_blocked_tokens_and_length_are_junk_without_embedding():
    embed = make_embed_fn({"clean keyword": _unit(1, 0)})
    r = run_relevance_gate(
        per_topic={"t1": {
            "clean keyword": ["keyword_ideas"],
            "best casino bonus": ["competitor"],   # blocked token -> junk
            "x": ["autocomplete"],                  # too short -> junk
        }},
        topic_embeddings={"t1": _unit(1, 0)},
        embed_fn=embed,
        threshold=0.5,
    )
    by_kw = {g.keyword: g for g in r.per_topic["t1"]}
    assert by_kw["best casino bonus"].status == "filtered_junk"
    assert by_kw["x"].status == "filtered_junk"
    assert by_kw["clean keyword"].status == "active"
    # junk never gets embedded; only the one clean candidate batch
    assert embed.calls["n"] == 1


def test_relevance_threshold_splits_active_and_filtered():
    # anchor points along (1,0). "near" is aligned; "far" is orthogonal.
    vectors = {"near kw": _unit(1, 0.1), "far kw": _unit(0, 1)}
    embed = make_embed_fn(vectors)
    r = run_relevance_gate(
        per_topic={"t1": {"near kw": ["s"], "far kw": ["s"]}},
        topic_embeddings={"t1": _unit(1, 0)},
        embed_fn=embed,
        threshold=0.62,
    )
    by_kw = {g.keyword: g for g in r.per_topic["t1"]}
    assert by_kw["near kw"].status == "active"
    assert by_kw["near kw"].relevance_score > 0.62
    assert by_kw["near kw"].embedding is not None  # kept for clustering
    assert by_kw["far kw"].status == "filtered_relevance"
    assert by_kw["far kw"].relevance_score < 0.62
    assert by_kw["far kw"].embedding is None  # only active keeps its vector


def test_missing_topic_embedding_keeps_active_and_degrades():
    embed = make_embed_fn({})
    r = run_relevance_gate(
        per_topic={"t1": {"some kw": ["s"]}},
        topic_embeddings={"t1": None},
        embed_fn=embed,
        topic_names={"t1": "Mechanism"},
        threshold=0.62,
    )
    g = r.per_topic["t1"][0]
    assert g.status == "active"
    assert g.relevance_score is None
    assert any("Mechanism" in n for n in r.degraded_notes)
    assert embed.calls["n"] == 0  # never embedded


def test_counts_summary():
    vectors = {"near kw": _unit(1, 0), "far kw": _unit(0, 1)}
    embed = make_embed_fn(vectors)
    r = run_relevance_gate(
        per_topic={"t1": {"near kw": ["s"], "far kw": ["s"], "xxx porn": ["competitor"]}},
        topic_embeddings={"t1": _unit(1, 0)},
        embed_fn=embed,
        threshold=0.62,
    )
    assert r.counts() == {"active": 1, "filtered_relevance": 1, "filtered_junk": 1}


def test_gated_keyword_dataclass_defaults():
    g = GatedKeyword("kw", ["s"], "active")
    assert g.relevance_score is None and g.embedding is None
