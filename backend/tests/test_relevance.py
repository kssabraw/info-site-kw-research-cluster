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


def test_platform_terms_are_junk_but_substrings_are_safe():
    embed = make_embed_fn({
        "retatrutide dosage": _unit(1, 0),
        "redditor community": _unit(1, 0),  # 'redditor' != 'reddit' -> not blocked
    })
    r = run_relevance_gate(
        per_topic={"t1": {
            "retatrutide dosage": ["keyword_ideas"],
            "retatrutide reddit": ["keyword_suggestions"],   # platform -> junk
            "retatrutide review youtube": ["autocomplete"],  # platform -> junk
            "best retatrutide forum": ["competitor"],        # platform -> junk
            "redditor community": ["competitor"],            # whole-word: safe
        }},
        topic_embeddings={"t1": _unit(1, 0)},
        embed_fn=embed,
        threshold=0.5,
    )
    by_kw = {g.keyword: g for g in r.per_topic["t1"]}
    assert by_kw["retatrutide reddit"].status == "filtered_junk"
    assert by_kw["retatrutide review youtube"].status == "filtered_junk"
    assert by_kw["best retatrutide forum"].status == "filtered_junk"
    assert by_kw["retatrutide dosage"].status == "active"
    assert by_kw["redditor community"].status == "active"


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
    assert r.counts() == {"active": 1, "filtered_relevance": 1,
                          "filtered_junk": 1, "filtered_language": 0}


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


def test_past_year_keyword_filtered_as_junk():
    # "best vpn 2024" carries a year strictly before the (test-injected)
    # current year and no current/future year -> filtered_junk before the
    # embed call (so no embedding is wasted).
    embed = make_embed_fn({"best vpn": _unit(1, 0)})
    r = run_relevance_gate(
        per_topic={"t1": {
            "best vpn": ["x"],          # no year -> kept (scored)
            "best vpn 2024": ["x"],     # past -> junk
            "best vpn 2023": ["x"],     # past -> junk
        }},
        topic_embeddings={"t1": _unit(1, 0)},
        embed_fn=embed,
        threshold=0.5,
        current_year=2026,
    )
    by_kw = {g.keyword: g.status for g in r.per_topic["t1"]}
    assert by_kw["best vpn 2024"] == "filtered_junk"
    assert by_kw["best vpn 2023"] == "filtered_junk"
    assert by_kw["best vpn"] == "active"


def test_current_or_future_year_keyword_kept():
    embed = make_embed_fn({
        "best vpn 2026": _unit(1, 0),
        "best vpn 2027 predictions": _unit(1, 0),
    })
    r = run_relevance_gate(
        per_topic={"t1": {
            "best vpn 2026": ["x"],              # current year -> kept
            "best vpn 2027 predictions": ["x"],  # future year -> kept
        }},
        topic_embeddings={"t1": _unit(1, 0)},
        embed_fn=embed,
        threshold=0.5,
        current_year=2026,
    )
    by_kw = {g.keyword: g.status for g in r.per_topic["t1"]}
    assert by_kw["best vpn 2026"] == "active"
    assert by_kw["best vpn 2027 predictions"] == "active"


def test_past_year_with_current_year_kept_as_comparison():
    # A keyword that names BOTH a past and the current year is a comparison
    # ("ipad 2024 vs 2026"); the past-year filter must not drop it.
    embed = make_embed_fn({"ipad 2024 vs 2026": _unit(1, 0)})
    r = run_relevance_gate(
        per_topic={"t1": {"ipad 2024 vs 2026": ["x"]}},
        topic_embeddings={"t1": _unit(1, 0)},
        embed_fn=embed,
        threshold=0.5,
        current_year=2026,
    )
    by_kw = {g.keyword: g.status for g in r.per_topic["t1"]}
    assert by_kw["ipad 2024 vs 2026"] == "active"


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


def test_language_filter_tags_non_english_before_embedding():
    # The lingua-py detector is injected as a stub: every keyword in the set is
    # "non-English". They must be tagged filtered_language and NEVER embedded
    # (no embedding cost spent on something we just filtered out).
    embed = make_embed_fn({"english kw": _unit(1, 0)})
    non_english = {"wat is een managed service provider",
                   "was ist eine managed service provider"}

    def lang_filter(kw):
        return kw in non_english

    r = run_relevance_gate(
        per_topic={"t1": {
            "english kw": ["x"],
            "wat is een managed service provider": ["x"],
            "was ist eine managed service provider": ["x"],
        }},
        topic_embeddings={"t1": _unit(1, 0)},
        embed_fn=embed,
        threshold=0.5,
        language_filter=lang_filter,
    )
    by_kw = {g.keyword: g for g in r.per_topic["t1"]}
    assert by_kw["wat is een managed service provider"].status == "filtered_language"
    assert by_kw["was ist eine managed service provider"].status == "filtered_language"
    assert by_kw["wat is een managed service provider"].relevance_score is None
    assert by_kw["wat is een managed service provider"].embedding is None
    assert by_kw["english kw"].status == "active"
    # Counts surface the new bucket; only the surviving candidate was embedded.
    assert r.counts()["filtered_language"] == 2
    # The English candidate was embedded once.
    assert embed.calls["n"] == 1


def test_language_filter_off_by_default_keeps_everything():
    # No language_filter supplied -> the gate runs as before (no filter).
    embed = make_embed_fn({"wat is een managed service provider": _unit(1, 0)})
    r = run_relevance_gate(
        per_topic={"t1": {"wat is een managed service provider": ["x"]}},
        topic_embeddings={"t1": _unit(1, 0)},
        embed_fn=embed,
        threshold=0.5,
    )
    assert r.per_topic["t1"][0].status == "active"
    assert r.counts()["filtered_language"] == 0


def test_language_filter_detected_once_per_unique_keyword():
    # A keyword fanned into many silos must be detected ONCE — the cache
    # prevents N model calls for N silo memberships.
    calls = {"n": 0}

    def lang_filter(kw):
        calls["n"] += 1
        return kw == "wat is een vraag"

    embed = make_embed_fn({"english kw": _unit(1, 0)})
    r = run_relevance_gate(
        per_topic={
            "A": {"wat is een vraag": ["x"], "english kw": ["x"]},
            "B": {"wat is een vraag": ["x"], "english kw": ["x"]},
            "C": {"wat is een vraag": ["x"]},
        },
        topic_embeddings={"A": _unit(1, 0), "B": _unit(1, 0), "C": _unit(1, 0)},
        embed_fn=embed,
        threshold=0.5,
        language_filter=lang_filter,
    )
    # Exactly 2 unique keywords -> at most 2 detector calls (cache hits otherwise).
    assert calls["n"] == 2
    for tid in ("A", "B", "C"):
        statuses = {g.keyword: g.status for g in r.per_topic[tid]}
        assert statuses["wat is een vraag"] == "filtered_language"


def test_junk_filter_runs_first_and_language_filter_is_not_called_for_junk():
    # Junk is the cheapest gate (regex check, no model call) and applies first.
    # A keyword that is BOTH junk and non-English is tagged filtered_junk, never
    # passed to the language detector (so a regression in junk-first ordering
    # would show up as the detector seeing a junk keyword).
    seen: list[str] = []

    def lang_filter(kw):
        seen.append(kw)
        return True  # claim everything is non-English

    embed = make_embed_fn({"clean kw": _unit(1, 0)})
    r = run_relevance_gate(
        per_topic={"t1": {
            "clean kw": ["x"],
            "best casino bonus": ["x"],  # blocked token -> junk first
        }},
        topic_embeddings={"t1": _unit(1, 0)},
        embed_fn=embed,
        threshold=0.5,
        language_filter=lang_filter,
    )
    by_kw = {g.keyword: g.status for g in r.per_topic["t1"]}
    assert by_kw["best casino bonus"] == "filtered_junk"
    # Junk shortcuts before the language detector even runs.
    assert "best casino bonus" not in seen


def test_language_filter_swallows_per_call_errors():
    # A misbehaving detector (raises on a specific keyword) must NOT abort the
    # gate; the keyword stays in (False = keep) and the rest are detected.
    def lang_filter(kw):
        if kw == "exploder":
            raise RuntimeError("model died")
        return kw == "wat is een vraag"

    embed = make_embed_fn({"exploder": _unit(1, 0), "english kw": _unit(1, 0)})
    r = run_relevance_gate(
        per_topic={"t1": {
            "exploder": ["x"],
            "english kw": ["x"],
            "wat is een vraag": ["x"],
        }},
        topic_embeddings={"t1": _unit(1, 0)},
        embed_fn=embed,
        threshold=0.5,
        language_filter=lang_filter,
    )
    by_kw = {g.keyword: g.status for g in r.per_topic["t1"]}
    assert by_kw["exploder"] == "active"            # detector error -> keep
    assert by_kw["english kw"] == "active"
    assert by_kw["wat is een vraag"] == "filtered_language"
