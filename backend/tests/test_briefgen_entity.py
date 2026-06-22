"""M13 slice 3 — main-entity derivation (X.2) pure tests (no spaCy / no OpenAI).

`np_extract` and `embed_fn` are injected stubs, so the scoring/clustering/confidence
logic is fully deterministic and sandbox-runnable (aio §13.X.8 test list a-g)."""

import itertools

from app.briefgen.entity import NounPhrase, cluster_phrases, derive_main_entity


def _np(raw, norm, head, subj=False, org=False):
    return NounPhrase(raw=raw, norm=norm, head_lemma=head, is_subject=subj, is_org=org)


def _extractor(by_text):
    return lambda text: by_text.get(text, [])


def _embed(mapping, default=(0.0, 0.0, 1.0)):
    return lambda texts: [list(mapping.get(t, default)) for t in texts]


def test_a_angel_number_canonical_with_query_variant():
    phrases = [_np("angel number 327", "angel number 327", "327", subj=(i == 0)) for i in range(3)]
    phrases.append(_np("327 angel number", "327 angel number", "327"))
    me = derive_main_entity(
        aio_answer="A", aio_present=True, title="Angel Number 327 Meaning",
        keyword="327 angel number", np_extract=_extractor({"A": phrases}),
        embed_fn=_embed({"327 angel number": (1, 0, 0), "angel number 327": (1, 0, 0)}),
    )
    assert me.source == "aio" and me.canonical == "angel number 327"
    assert "327 angel number" in me.variants


def test_b_generic_head_suppressed():
    phrases = [_np("benefits", "benefit", "benefit") for _ in range(3)]
    phrases += [_np("magnesium glycinate benefits", "magnesium glycinate benefit", "benefit", subj=(i == 0)) for i in range(3)]
    me = derive_main_entity(
        aio_answer="A", aio_present=True, title="Magnesium Glycinate Benefits",
        keyword="magnesium glycinate", np_extract=_extractor({"A": phrases}),
        embed_fn=_embed({"magnesium glycinate": (1, 0, 0), "magnesium glycinate benefits": (1, 0, 0)}),
    )
    assert me.canonical == "magnesium glycinate benefits"   # generic "benefits" demoted


def test_c_comparison_triggers_multi_entity_and_title_break():
    phrases = [_np("retatrutide", "retatrutide", "retatrutide", subj=(i == 0)) for i in range(3)]
    phrases += [_np("tirzepatide", "tirzepatide", "tirzepatide", subj=(i == 0)) for i in range(3)]
    me = derive_main_entity(
        aio_answer="A", aio_present=True, title="Retatrutide vs Tirzepatide",
        keyword="retatrutide vs tirzepatide", comparison_intent=True,
        np_extract=_extractor({"A": phrases}),
        embed_fn=_embed({
            "retatrutide": (1, 0, 0), "tirzepatide": (0, 1, 0),
            "Retatrutide vs Tirzepatide": (1, 0, 0),
            "retatrutide vs tirzepatide": (1, 0, 0),
        }),
    )
    assert me.multi_entity_flag is True
    assert me.canonical == "retatrutide" and me.secondary_entity == "tirzepatide"


def test_d_sanity_failure_falls_back_to_title():
    phrases = [_np("zodiac signs", "zodiac sign", "sign", subj=(i == 0)) for i in range(4)]
    me = derive_main_entity(
        aio_answer="A", aio_present=True, title="Best Magnesium Glycinate Dose",
        keyword="magnesium glycinate",
        np_extract=_extractor({
            "A": phrases,
            "Best Magnesium Glycinate Dose": [_np("magnesium glycinate dose", "magnesium glycinate dose", "dose")],
        }),
        embed_fn=_embed({
            "zodiac signs": (0, 1, 0),                 # off-topic -> sanity cosine 0 < 0.45
            "magnesium glycinate": (1, 0, 0),
            "magnesium glycinate dose": (1, 0, 0),
        }),
    )
    assert me.source == "title_fallback" and me.canonical == "magnesium glycinate dose"


def test_e_aio_absent_title_fallback_deterministic():
    me = derive_main_entity(
        aio_answer="", aio_present=False, title="Retatrutide Guide", keyword="retatrutide",
        np_extract=_extractor({"Retatrutide Guide": [
            _np("retatrutide guide", "retatrutide guide", "guide"),
            _np("retatrutide", "retatrutide", "retatrutide"),
        ]}),
        embed_fn=_embed({"retatrutide": (1, 0, 0), "retatrutide guide": (0.7, 0.1, 0)}),
    )
    assert me.source == "title_fallback" and me.canonical == "retatrutide"


def test_f_brand_org_excluded():
    phrases = [_np("Healthline", "healthline", "healthline", org=True) for _ in range(5)]
    phrases += [_np("magnesium glycinate", "magnesium glycinate", "glycinate", subj=(i == 0)) for i in range(3)]
    me = derive_main_entity(
        aio_answer="A", aio_present=True, title="Magnesium Glycinate", keyword="magnesium glycinate",
        np_extract=_extractor({"A": phrases}),
        embed_fn=_embed({"magnesium glycinate": (1, 0, 0)}),
    )
    assert me.canonical == "magnesium glycinate"   # 5x Healthline excluded as ORG


def test_clustering_is_order_independent():
    """Union-find clustering must give the same result for any input order (the greedy
    first-match version was order-dependent)."""
    a = _np("number 327", "number 327", "number")
    b = _np("angel number 327", "angel number 327", "number")   # superset, same head
    c = _np("327 angel number", "327 angel number", "number")   # token-set-equal to b
    outcomes = set()
    for perm in itertools.permutations([a, b, b, c]):
        clusters = cluster_phrases(list(perm))
        outcomes.add((len(clusters), clusters[0].canonical))
    assert outcomes == {(1, "angel number 327")}   # always one cluster, same canonical


def test_g_determinism():
    phrases = [_np("magnesium glycinate", "magnesium glycinate", "glycinate", subj=(i == 0)) for i in range(4)]
    kwargs = dict(
        aio_answer="A", aio_present=True, title="Magnesium Glycinate", keyword="magnesium glycinate",
        np_extract=_extractor({"A": phrases}), embed_fn=_embed({"magnesium glycinate": (1, 0, 0)}),
    )
    a, b = derive_main_entity(**kwargs), derive_main_entity(**kwargs)
    assert (a.canonical, a.source, a.variants) == (b.canonical, b.source, b.variants)


def test_strip_leading_stopwords():
    from app.briefgen.entity import _strip_leading_stopwords

    assert _strip_leading_stopwords("Is Retatrutide") == "Retatrutide"
    assert _strip_leading_stopwords("How to Lose Weight") == "Lose Weight"
    assert _strip_leading_stopwords("the best mattress") == "best mattress"
    assert _strip_leading_stopwords("Retatrutide") == "Retatrutide"   # unchanged
    assert _strip_leading_stopwords("is are the") == "the"            # keeps >=1 token
