"""LLM routing for ambiguous keywords — gate second-pass.

Unit coverage of the router factory (build_llm_router) and the gate
integration (run_relevance_gate's llm_router hook). LLM calls are
monkeypatched, so no egress.
"""

from app.pipeline.llm_router import build_llm_router
from app.pipeline.relevance import run_relevance_gate


class _FakeLLM:
    def __init__(self, picks_by_kw: dict[str, str]):
        self.picks_by_kw = picks_by_kw
        self.batches: list[list[str]] = []

    def route_ambiguous_keywords(self, *, seed, silos, keywords):
        self.batches.append(list(keywords))
        return {kw: self.picks_by_kw[kw] for kw in keywords
                if kw in self.picks_by_kw}


def test_router_only_reroutes_within_candidate_silos():
    """If the LLM picks a silo that wasn't in the keyword's candidate list,
    the cosine pick stands (defensive)."""
    llm = _FakeLLM({"kw1": "s_bad", "kw2": "s2"})
    router = build_llm_router(
        seed="thing", silos=[{"id": "s1"}, {"id": "s2"}], llm=llm,
        batch_size=10, max_workers=1,
    )
    result = router([("kw1", ["s1", "s2"]), ("kw2", ["s1", "s2"])])
    # kw1's pick "s_bad" is rejected (not in candidates); kw2 is honored.
    assert result == {"kw2": "s2"}


def test_router_batches_ambiguous_keywords():
    keywords = [f"kw{i}" for i in range(7)]
    llm = _FakeLLM({k: "s1" for k in keywords})
    router = build_llm_router(
        seed="thing", silos=[{"id": "s1"}, {"id": "s2"}], llm=llm,
        batch_size=3, max_workers=2,
    )
    ambiguous = [(kw, ["s1", "s2"]) for kw in keywords]
    out = router(ambiguous)
    # 7 keywords / batch=3 -> 3 batches (3, 3, 1).
    assert len(llm.batches) == 3
    assert {kw for batch in llm.batches for kw in batch} == set(keywords)
    assert out == {kw: "s1" for kw in keywords}


def test_router_returns_empty_on_failure_does_not_raise():
    class _BoomLLM:
        def route_ambiguous_keywords(self, **_):
            raise RuntimeError("transient")

    router = build_llm_router(
        seed="thing", silos=[{"id": "s1"}], llm=_BoomLLM(),
        batch_size=10, max_workers=1,
    )
    out = router([("kw", ["s1"])])
    assert out == {}  # benign degrade; gate keeps cosine routing


def test_router_noop_when_no_silos_or_no_ambiguous():
    router = build_llm_router(
        seed="thing", silos=[], llm=_FakeLLM({}), batch_size=10, max_workers=1,
    )
    assert router([("kw", ["s1"])]) == {}

    router2 = build_llm_router(
        seed="thing", silos=[{"id": "s1"}], llm=_FakeLLM({}),
        batch_size=10, max_workers=1,
    )
    assert router2([]) == {}


# ---- gate integration --------------------------------------------------


def _embed_fn(mapping):
    def embed(batch):
        return [mapping[k] for k in batch]
    return embed


def test_gate_calls_llm_router_only_for_ambiguous_below_margin():
    """A keyword with a clear cosine winner (margin > threshold) does not go
    through the LLM router; an ambiguous one does — and the router's pick wins."""
    # anchor s1 = (1,0); s2 = (0.7, 0.71) -> s2 slightly tilted off s1.
    # kw_clear at (1,0) -> s1 wins by a big margin (no LLM call).
    # kw_ambig at (0.71, 0.71) -> both anchors give very close cosines (~0.71
    # and ~0.998) — actually no, let's craft: anchor s1=(0.99, 0.14),
    # s2=(0.14, 0.99); kw=(0.71, 0.71) -> cosines ~0.798 and ~0.797 (tight).
    anchors = {"s1": [0.99, 0.14], "s2": [0.14, 0.99]}
    embeds = {
        "kw_clear": [1.0, 0.0],          # ~0.99 vs s1, ~0.14 vs s2 — easy s1
        "kw_ambig": [0.71, 0.71],        # ~0.80 vs s1, ~0.80 vs s2 — ambiguous
    }
    captured: list[list[tuple[str, list[str]]]] = []

    def router(ambiguous):
        captured.append(list(ambiguous))
        # Pretend the LLM picked s2 for the ambiguous kw.
        return {kw: "s2" for kw, _ in ambiguous}

    result = run_relevance_gate(
        per_topic={
            "s1": {"kw_clear": ["src"], "kw_ambig": ["src"]},
            "s2": {"kw_clear": ["src"], "kw_ambig": ["src"]},
        },
        topic_embeddings=anchors,
        embed_fn=_embed_fn(embeds),
        threshold=0.0,                # we don't care about the score gate here
        assign_best_silo=True,
        llm_router=router,
        llm_router_margin=0.05,       # 0.05 is well above the tight ambig case
    )

    # Only the ambiguous kw was sent to the router.
    assert len(captured) == 1
    sent = captured[0]
    assert len(sent) == 1 and sent[0][0] == "kw_ambig"
    # kw_clear still active in s1; kw_ambig active in s2 (LLM picked s2).
    s1_active = {g.keyword for g in result.per_topic["s1"] if g.status == "active"}
    s2_active = {g.keyword for g in result.per_topic["s2"] if g.status == "active"}
    assert s1_active == {"kw_clear"}
    assert s2_active == {"kw_ambig"}


def test_gate_without_router_keeps_cosine_routing():
    """No router supplied -> behavior is unchanged from pure Lever-3."""
    anchors = {"s1": [1.0, 0.0], "s2": [0.0, 1.0]}
    embeds = {"kw": [0.6, 0.8]}  # cosine: 0.6 vs s1, 0.8 vs s2 -> s2 wins
    result = run_relevance_gate(
        per_topic={"s1": {"kw": ["src"]}, "s2": {"kw": ["src"]}},
        topic_embeddings=anchors,
        embed_fn=_embed_fn(embeds),
        threshold=0.0,
        assign_best_silo=True,
    )
    s2_active = {g.keyword for g in result.per_topic["s2"] if g.status == "active"}
    assert s2_active == {"kw"}
