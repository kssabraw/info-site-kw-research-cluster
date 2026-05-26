"""Salience split — divide an over-large article into sub-articles (PRD §7.10).

Pure unit tests with a deterministic fake embed_fn (two orthogonal directions =>
two clean sub-clusters), so Louvain's split is predictable without any egress.
"""

from app.pipeline.article_planning.models import ArticleRecord, PlanResult, TopicPlan
from app.pipeline.article_planning.split import split_oversized_articles


def _embed_two_groups(group_b: set[str]):
    """A keyword in group_b -> direction [0,1], else -> [1,0]. The two groups have
    cosine 0 between them and 1 within, so they form two Louvain communities."""
    def embed(keywords: list[str]) -> list[list[float]]:
        return [[0.0, 1.0] if k in group_b else [1.0, 0.0] for k in keywords]
    return embed


def _article(primary: str, supporting: list[str]) -> ArticleRecord:
    return ArticleRecord(
        topic_id="t1", primary_keyword=primary, supporting_keywords=supporting,
        intent="informational", suggested_h2s=["H2 a", "H2 b"],
        source_statistical_grouping_id="t1:g0", orchestrator_notes="orig",
    )


def _result(art: ArticleRecord) -> PlanResult:
    return PlanResult(per_topic=[TopicPlan(topic_id="t1", articles=[art])])


def test_oversized_article_splits_into_two():
    a_kws = [f"a{i}" for i in range(8)]          # group A (primary in here)
    b_kws = [f"b{i}" for i in range(8)]          # group B
    art = _article("a0", a_kws[1:] + b_kws)      # 16 keywords total
    result = _result(art)

    split_oversized_articles(
        result, embed_fn=_embed_two_groups(set(b_kws)),
        min_keywords=10, resolution=1.0, edge_threshold=0.5, min_subarticle_size=3,
    )

    arts = result.per_topic[0].articles
    assert len(arts) == 2
    # The original primary is kept in its sub-article with its editorial fields.
    keeper = next(a for a in arts if a.primary_keyword == "a0")
    assert keeper.suggested_h2s == ["H2 a", "H2 b"]
    assert keeper.source_statistical_grouping_id == "t1:g0"
    # The other sub-article is led by a group-B medoid and is fresh.
    other = next(a for a in arts if a.primary_keyword != "a0")
    assert other.primary_keyword in b_kws
    assert other.suggested_h2s == []
    assert other.source_statistical_grouping_id is None
    # No keyword is lost or duplicated across the split.
    all_kws = {a.primary_keyword for a in arts} | {
        k for a in arts for k in a.supporting_keywords
    }
    assert all_kws == set(a_kws + b_kws)
    assert result.per_topic[0].log["salience_split_added"] == 1


def test_small_article_is_left_untouched():
    art = _article("p", ["k1", "k2", "k3"])
    result = _result(art)
    split_oversized_articles(
        result, embed_fn=_embed_two_groups({"k2"}),
        min_keywords=40, resolution=1.5, edge_threshold=0.55, min_subarticle_size=5,
    )
    assert len(result.per_topic[0].articles) == 1
    assert "salience_split_added" not in result.per_topic[0].log


def test_cohesive_article_does_not_split():
    # All keywords in one direction -> one community -> no split even when large.
    kws = [f"k{i}" for i in range(30)]
    art = _article("k0", kws[1:])
    result = _result(art)
    split_oversized_articles(
        result, embed_fn=_embed_two_groups(set()),  # everything group A
        min_keywords=10, resolution=1.0, edge_threshold=0.5, min_subarticle_size=3,
    )
    assert len(result.per_topic[0].articles) == 1


def test_tiny_subcluster_folds_into_largest_no_thin_stub():
    # Group B has only 2 members; with min_subarticle_size=5 it should fold back
    # into the large group A rather than spawn a 2-keyword stub article.
    a_kws = [f"a{i}" for i in range(20)]
    b_kws = ["b0", "b1"]
    art = _article("a0", a_kws[1:] + b_kws)
    result = _result(art)
    split_oversized_articles(
        result, embed_fn=_embed_two_groups(set(b_kws)),
        min_keywords=10, resolution=1.0, edge_threshold=0.5, min_subarticle_size=5,
    )
    assert len(result.per_topic[0].articles) == 1  # no split — B too small
