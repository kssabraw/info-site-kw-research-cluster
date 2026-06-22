"""M13 follow-up (2b) — clustered-keyword coverage audit (pure core)."""

from app.briefgen.coverage import (
    _dedupe,
    _lexically_covered,
    _tokens,
    as_h3_candidates,
    audit,
    greedy_group,
)


def _bag_embed(texts):
    """Deterministic bag-of-tokens vectors over a small vocab (cosine ~ token overlap)."""
    vocab = ["retatrutide", "amino", "acid", "sequence", "structure", "dosing",
             "side", "effects", "molecule", "peptide", "half", "life"]
    return [[1.0 if w in _tokens(t) else 0.0 for w in vocab] for t in texts]


def test_dedupe_case_insensitive_keeps_order():
    assert _dedupe(["A", "a ", "B", "", "b"]) == ["A", "B"]


def test_lexical_subset_match():
    headings = [_tokens("Retatrutide Amino Acid Sequence Explained")]
    assert _lexically_covered("retatrutide amino acid sequence", headings)
    assert not _lexically_covered("retatrutide half life", headings)


def test_as_h3_candidates_tags_source_and_dedups():
    cands = as_h3_candidates(["x", "x", "Y"])
    assert [(c.text, c.source) for c in cands] == [("x", "cluster_keyword"), ("Y", "cluster_keyword")]


def test_audit_covered_lexical_used_and_uncovered():
    headings = ["Retatrutide Amino Acid Sequence", "Retatrutide Dosing Schedule"]
    supporting = [
        "retatrutide amino acid sequence",   # lexical subset -> covered
        "retatrutide molecule",              # promoted to subtopic -> covered via used_texts
        "retatrutide aa sequence",           # high cosine to the sequence heading -> covered
        "retatrutide half life",             # nothing close -> uncovered
    ]
    res = audit(
        supporting, heading_texts=headings, used_texts=["Retatrutide Molecule"],
        embed_fn=_bag_embed, threshold=0.62,
    )
    assert res["total"] == 4
    assert "retatrutide half life" in [u["keyword"] for u in res["uncovered"]]
    assert res["uncovered_count"] == 1 and res["covered_count"] == 3
    assert "Retatrutide Molecule" in res["used_as_subtopic"]
    # the uncovered entry carries its nearest heading + cosine for owner triage
    u = res["uncovered"][0]
    assert u["nearest"] in headings and 0.0 <= u["cosine"] <= 1.0


def test_audit_empty_supporting_is_safe():
    res = audit([], heading_texts=["H"], used_texts=[], embed_fn=_bag_embed, threshold=0.62)
    assert res["total"] == 0 and res["covered"] == [] and res["uncovered"] == []


def test_audit_no_headings_marks_all_uncovered():
    res = audit(["a", "b"], heading_texts=[], used_texts=[], embed_fn=_bag_embed, threshold=0.62)
    assert {u["keyword"] for u in res["uncovered"]} == {"a", "b"}


def test_greedy_group_collapses_near_duplicates():
    # Two structure phrasings cluster together; the half-life one stands alone.
    texts = ["retatrutide amino acid sequence", "retatrutide aa sequence", "retatrutide half life"]
    vecs = _bag_embed(texts)
    groups = greedy_group(texts, vecs, threshold=0.5)
    # the two sequence phrasings share a group; half-life is its own
    assert any(set(g) == {"retatrutide amino acid sequence", "retatrutide aa sequence"} for g in groups)
    assert ["retatrutide half life"] in groups
    # every keyword lands in exactly one group
    assert sorted(k for g in groups for k in g) == sorted(texts)
