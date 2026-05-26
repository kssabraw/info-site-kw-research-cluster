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


def test_embeds_each_unique_keyword_once_across_silos():
    # "shared kw" appears in both silos; it must be embedded once, not per-silo.
    vectors = {"shared kw": _unit(1, 0), "t1 only": _unit(1, 0), "t2 only": _unit(1, 0)}
    seen_batches: list[list[str]] = []

    def embed(texts):
        seen_batches.append(list(texts))
        return [vectors[t] for t in texts]

    r = run_relevance_gate(
        per_topic={
            "t1": {"shared kw": ["s"], "t1 only": ["s"]},
            "t2": {"shared kw": ["s"], "t2 only": ["s"]},
        },
        topic_embeddings={"t1": _unit(1, 0), "t2": _unit(1, 0)},
        embed_fn=embed,
        threshold=0.5,
    )
    embedded = [kw for batch in seen_batches for kw in batch]
    assert embedded.count("shared kw") == 1
    assert sorted(embedded) == ["shared kw", "t1 only", "t2 only"]
    # The single vector is reused: shared kw is active in both silos.
    assert any(g.keyword == "shared kw" and g.status == "active" for g in r.per_topic["t1"])
    assert any(g.keyword == "shared kw" and g.status == "active" for g in r.per_topic["t2"])


def test_health_terms_not_blocked_as_junk():
    # "sex" and "bet" were removed from the blocklist; legit terms must survive.
    vectors = {"retatrutide sex drive": _unit(1, 0), "best bet supplement": _unit(1, 0)}
    embed = make_embed_fn(vectors)
    r = run_relevance_gate(
        per_topic={"t1": {"retatrutide sex drive": ["s"], "best bet supplement": ["s"]}},
        topic_embeddings={"t1": _unit(1, 0)},
        embed_fn=embed,
        threshold=0.5,
    )
    statuses = {g.keyword: g.status for g in r.per_topic["t1"]}
    assert statuses["retatrutide sex drive"] == "active"
    assert statuses["best bet supplement"] == "active"
    # casino/xxx stay blocked
    r2 = run_relevance_gate(
        per_topic={"t1": {"online casino tips": ["s"]}},
        topic_embeddings={"t1": _unit(1, 0)},
        embed_fn=make_embed_fn({}),
        threshold=0.5,
    )
    assert r2.per_topic["t1"][0].status == "filtered_junk"


def test_embedding_failure_keeps_active_and_degrades_without_aborting():
    def embed(_texts):
        raise RuntimeError("openai 503")

    r = run_relevance_gate(
        per_topic={"t1": {"kw one": ["s"], "kw two": ["s"]}},
        topic_embeddings={"t1": _unit(1, 0)},
        embed_fn=embed,
        threshold=0.62,
    )
    statuses = {g.keyword: g.status for g in r.per_topic["t1"]}
    assert statuses == {"kw one": "active", "kw two": "active"}
    assert all(g.relevance_score is None for g in r.per_topic["t1"])
    assert any("embedding service degraded" in n for n in r.degraded_notes)


def test_embedding_count_mismatch_degrades_not_silently_truncates():
    # embed_fn returns fewer vectors than asked -> the whole batch is dropped
    # (kept active), never zip-truncated so no keyword silently vanishes.
    def embed(_texts):
        return [_unit(1, 0)]  # 1 vector for 2 inputs

    r = run_relevance_gate(
        per_topic={"t1": {"kw one": ["s"], "kw two": ["s"]}},
        topic_embeddings={"t1": _unit(1, 0)},
        embed_fn=embed,
        threshold=0.62,
    )
    statuses = {g.keyword: g.status for g in r.per_topic["t1"]}
    assert set(statuses) == {"kw one", "kw two"}  # neither dropped
    assert all(s == "active" for s in statuses.values())
    assert any("embedding service degraded" in n for n in r.degraded_notes)


def test_peer_entity_filter_drops_competitor_not_seed():
    # tirzepatide (a peer) without retatrutide -> off-niche junk; "vs retatrutide"
    # keeps it; the generic mechanism uses supplied seed/peer lists (no hardcoding).
    embed = make_embed_fn({
        "retatrutide dosage": _unit(1, 0),
        "tirzepatide vs retatrutide": _unit(1, 0),
        "reta peptide results": _unit(1, 0),
    })
    r = run_relevance_gate(
        per_topic={"t1": {
            "retatrutide dosage": ["x"],
            "buy tirzepatide injection": ["x"],   # peer, no seed -> junk
            "tirzepatide vs retatrutide": ["x"],  # peer + seed -> kept
            "reta peptide results": ["x"],        # alias -> kept
            "clinical trials europe": ["x"],      # no peer, no seed -> not peer-filtered
        }},
        topic_embeddings={"t1": _unit(1, 0)},
        embed_fn=embed,
        threshold=0.5,
        seed_terms=["retatrutide", "reta"],
        peer_terms=["tirzepatide", "semaglutide", "ozempic"],
    )
    by_kw = {g.keyword: g.status for g in r.per_topic["t1"]}
    assert by_kw["buy tirzepatide injection"] == "filtered_junk"
    assert by_kw["tirzepatide vs retatrutide"] == "active"
    assert by_kw["reta peptide results"] == "active"
    assert by_kw["retatrutide dosage"] == "active"
    # not a peer and not seed -> NOT peer-filtered (left to the relevance score)
    assert by_kw["clinical trials europe"] != "filtered_junk"


def test_assign_best_silo_routes_keyword_to_one_silo():
    # "kw" is fanned into both silos but embeds toward silo A; with Lever 3 it's
    # active only in A and filtered_relevance in B (no cross-silo duplicate).
    embed = make_embed_fn({"kw one": _unit(1, 0)})
    r = run_relevance_gate(
        per_topic={
            "A": {"kw one": ["x"]},
            "B": {"kw one": ["x"]},
        },
        topic_embeddings={"A": _unit(1, 0), "B": _unit(0, 1)},
        embed_fn=embed,
        threshold=0.5,
        assign_best_silo=True,
    )
    a = {g.keyword: g.status for g in r.per_topic["A"]}
    b = {g.keyword: g.status for g in r.per_topic["B"]}
    assert a["kw one"] == "active"               # best silo keeps it
    assert b["kw one"] == "filtered_relevance"   # routed away from B


def test_without_assign_best_silo_keyword_stays_in_both():
    # Default (flag off): the keyword is active in every silo it passes.
    embed = make_embed_fn({"kw one": _unit(1, 0)})
    r = run_relevance_gate(
        per_topic={"A": {"kw one": ["x"]}, "B": {"kw one": ["x"]}},
        topic_embeddings={"A": _unit(1, 0), "B": _unit(1, 0)},
        embed_fn=embed,
        threshold=0.5,
    )
    assert {g.status for g in r.per_topic["A"]} == {"active"}
    assert {g.status for g in r.per_topic["B"]} == {"active"}
