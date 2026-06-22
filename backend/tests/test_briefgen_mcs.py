"""M13 slice 4 — Max Cosine Synthesis pure-core tests (no LLM / no embeddings).

Covers answer decomposition, the dual-space scalar blend, dual-space scoring with
injected vectors, and the greedy set-coverage selection (the synthesis)."""

from app.briefgen.mcs import (
    ScoredHeading,
    blended_score,
    score_headings,
    select_by_coverage,
    split_into_points,
)


def _sh(text, points, chatgpt=0.0):
    return ScoredHeading(
        text=text, point_cosines=list(points), chatgpt_cosine=chatgpt,
        aio_headline=max(points) if points else 0.0, blended=0.0,
    )


def test_split_into_points_sentences_and_fallback():
    a = "Retatrutide is a triple agonist. It targets GLP-1, GIP and glucagon! Trials show weight loss?"
    assert split_into_points(a) == [
        "Retatrutide is a triple agonist.",
        "It targets GLP-1, GIP and glucagon!",
        "Trials show weight loss?",
    ]
    assert split_into_points("no terminal punctuation here") == ["no terminal punctuation here"]
    assert split_into_points("") == []
    assert split_into_points("a. b. c.", max_points=2) == ["a.", "b."]


def test_blended_score_engine_aware():
    assert blended_score(0.8, 0.6, aio_present=True, chatgpt_present=True) == 0.7
    assert blended_score(0.8, 0.6, aio_present=True, chatgpt_present=False) == 0.8   # AIO only
    assert blended_score(0.8, 0.6, aio_present=False, chatgpt_present=True) == 0.6   # GPT only
    assert blended_score(0.8, 0.6, aio_present=False, chatgpt_present=False) == 0.0


def test_score_headings_dual_space():
    out = score_headings(
        ["entity does X"],
        cand_aio_vecs=[[1.0, 0.0, 0.0]],
        cand_3l_vecs=[[1.0, 0.0, 0.0]],
        point_aio_vecs=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],   # 2 answer points
        chatgpt_vec=[1.0, 0.0, 0.0],
        aio_present=True, chatgpt_present=True,
    )
    s = out[0]
    assert s.point_cosines[0] == 1.0 and s.point_cosines[1] == 0.0
    assert s.aio_headline == 1.0 and s.chatgpt_cosine == 1.0
    assert s.blended == 1.0   # 0.5*1 + 0.5*1


def test_select_prefers_coverage_over_redundancy():
    """After picking a heading that covers point 0, a heading covering a NEW point must
    beat a redundant near-duplicate of the first (the 'synthesis' property)."""
    a = _sh("A covers p0", [0.9, 0.1, 0.1])
    b = _sh("B duplicates p0", [0.9, 0.1, 0.1])
    c = _sh("C covers p1", [0.1, 0.9, 0.1])
    d = _sh("D covers p2", [0.1, 0.1, 0.9])
    sel = select_by_coverage([a, b, c, d], min_count=2, max_count=4, epsilon=0.01,
                             aio_present=True, chatgpt_present=False)
    texts = {s.text for s in sel}
    assert "B duplicates p0" not in texts            # redundant heading dropped
    assert texts == {"A covers p0", "C covers p1", "D covers p2"}


def test_select_respects_min_count_even_below_epsilon():
    # 5 redundant headings on the same single point: marginal gain is 0 after the first,
    # but min_count forces 3.
    cands = [_sh(f"h{i}", [0.9]) for i in range(5)]
    sel = select_by_coverage(cands, min_count=3, max_count=12, epsilon=0.01,
                             aio_present=True, chatgpt_present=False)
    assert len(sel) == 3


def test_select_caps_at_max_count():
    cands = [_sh(f"h{i}", [0.1 * (i + 1), 0.0, 0.0]) for i in range(10)]
    sel = select_by_coverage(cands, min_count=2, max_count=4, epsilon=0.0,
                             aio_present=True, chatgpt_present=False)
    assert len(sel) == 4


def test_select_honest_shortfall_never_pads():
    # only 2 candidates but min_count 3 -> returns 2, never invents headings.
    sel = select_by_coverage([_sh("a", [0.9]), _sh("b", [0.1, 0.9])],
                             min_count=3, max_count=12, epsilon=0.01,
                             aio_present=True, chatgpt_present=False)
    assert len(sel) == 2


def test_select_chatgpt_only_diminishing():
    # aio absent -> coverage is the ChatGPT target alone; picks descending chatgpt until
    # the marginal gain falls below epsilon.
    cands = [_sh("hi", [], chatgpt=0.9), _sh("mid", [], chatgpt=0.85), _sh("lo", [], chatgpt=0.2)]
    sel = select_by_coverage(cands, min_count=1, max_count=12, epsilon=0.1,
                             aio_present=False, chatgpt_present=True)
    # first: 0.9 (gain 0.9). second 'mid': marginal 0.85-0.9 -> 0 < 0.1 and len>=min -> stop.
    assert [s.text for s in sel] == ["hi"]
