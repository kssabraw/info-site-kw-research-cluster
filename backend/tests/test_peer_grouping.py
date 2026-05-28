"""Peer-entity-aware article grouping (owner-requested § 7.10 follow-up).

Unit tests for the deterministic peer-entity partition: keywords that name a
peer entity get pulled into a per-peer article, keywords that name multiple
peers form a multi-peer bucket, keywords that name no peer stay with the parent
article. Aggregates across the topic's planner-articles so all keywords naming
the same peer collapse into one article.
"""

from app.pipeline.article_planning.models import ArticleRecord, PlanResult, TopicPlan
from app.pipeline.article_planning.peer_grouping import group_by_peer_entity

SEED = ["retatrutide"]
PEERS = ["tirzepatide", "semaglutide", "ozempic", "mounjaro", "zepbound"]


def _art(primary: str, supporting: list[str], topic="t1") -> ArticleRecord:
    return ArticleRecord(
        topic_id=topic, primary_keyword=primary, supporting_keywords=supporting,
        intent="informational", suggested_h2s=["H2a", "H2b"],
        source_statistical_grouping_id="g1", orchestrator_notes="orig",
    )


def _plan(*articles: ArticleRecord) -> PlanResult:
    return PlanResult(per_topic=[TopicPlan(topic_id="t1", articles=list(articles))])


def _by_primary(result: PlanResult) -> dict[str, ArticleRecord]:
    return {a.primary_keyword: a for a in result.per_topic[0].articles}


def test_all_peer_named_article_dissolves_into_per_peer_articles():
    """The owner-reported case: a cluster primaried on one peer-naming keyword,
    with other peer-naming supporting keywords for *different* peers. Must split
    into one article per peer (parent dissolves)."""
    result = _plan(_art(
        primary="switching from tirzepatide to retatrutide",
        supporting=[
            "switching from zepbound to retatrutide",
            "switching from semaglutide to retatrutide",
        ],
    ))
    group_by_peer_entity(result, seed_terms=SEED, peer_terms=PEERS)

    arts = result.per_topic[0].articles
    assert len(arts) == 3  # one per peer; parent dissolved
    # Every article is a comparison-intent article with no SERP / no prior H2s.
    assert all(a.intent == "comparison" for a in arts)
    assert all(a.suggested_h2s == [] for a in arts)
    # Each peer has its own primary; the original "switching ... tirzepatide ..."
    # primary survives as the tirzepatide article's primary (it was the only kw
    # in that bucket).
    primaries = {a.primary_keyword for a in arts}
    assert "switching from tirzepatide to retatrutide" in primaries
    assert "switching from zepbound to retatrutide" in primaries
    assert "switching from semaglutide to retatrutide" in primaries
    # Each is a stand-alone primary with zero supporting (no min — by design).
    for a in arts:
        assert a.supporting_keywords == []


def test_non_peer_primary_keeps_parent_peers_pull_out():
    """A non-peer primary keeps its article; peer-named supporting kw move out."""
    result = _plan(_art(
        primary="retatrutide mechanism of action",
        supporting=[
            "retatrutide vs tirzepatide mechanism",
            "retatrutide weight loss mechanism",   # non-peer, stays
        ],
    ))
    group_by_peer_entity(result, seed_terms=SEED, peer_terms=PEERS)

    arts = _by_primary(result)
    assert "retatrutide mechanism of action" in arts
    parent = arts["retatrutide mechanism of action"]
    assert parent.supporting_keywords == ["retatrutide weight loss mechanism"]
    assert parent.intent == "informational"  # parent intent preserved
    assert parent.suggested_h2s == ["H2a", "H2b"]  # parent H2s preserved
    # And the tirzepatide-named keyword formed its own article.
    tirz = next(a for a in arts.values() if a.intent == "comparison")
    assert tirz.primary_keyword == "retatrutide vs tirzepatide mechanism"
    assert tirz.suggested_h2s == []


def test_aggregates_across_articles_in_same_topic():
    """Keywords naming the same peer in DIFFERENT planner-articles in the same
    topic collapse into ONE article (the owner intent: one per peer)."""
    result = _plan(
        _art("retatrutide dosage", ["retatrutide vs tirzepatide dosage"]),
        _art("retatrutide review", ["switching from tirzepatide to retatrutide"]),
    )
    group_by_peer_entity(result, seed_terms=SEED, peer_terms=PEERS)

    arts = result.per_topic[0].articles
    tirz_arts = [a for a in arts if a.intent == "comparison"
                 and "tirzepatide" in (a.orchestrator_notes or "")]
    assert len(tirz_arts) == 1, "must collapse to one tirzepatide article"
    tirz = tirz_arts[0]
    assert set([tirz.primary_keyword, *tirz.supporting_keywords]) == {
        "retatrutide vs tirzepatide dosage",
        "switching from tirzepatide to retatrutide",
    }


def test_cross_topic_aggregation_avoids_duplicate_peer_articles():
    """The Mechanism-disappears bug: peer-grouping was per-topic, so every silo
    that had a tirzepatide-naming keyword spawned its own tirzepatide article;
    cross-topic dedup then wiped the smaller silo. The cross-topic version puts
    EXACTLY ONE tirzepatide article into the plan, in the silo that contributed
    the most tirzepatide-keywords."""
    result = PlanResult(per_topic=[
        TopicPlan(topic_id="big_silo", articles=[
            _art("kw a", ["retatrutide vs tirzepatide", "retatrutide vs tirzepatide dosage"], topic="big_silo"),
        ]),
        TopicPlan(topic_id="small_silo", articles=[
            _art("kw b", ["switching from tirzepatide to retatrutide"], topic="small_silo"),
        ]),
    ])
    group_by_peer_entity(result, seed_terms=SEED, peer_terms=PEERS)

    tirz_in_big = [a for a in result.per_topic[0].articles
                   if a.intent == "comparison"
                   and "tirzepatide" in (a.orchestrator_notes or "")]
    tirz_in_small = [a for a in result.per_topic[1].articles
                     if a.intent == "comparison"
                     and "tirzepatide" in (a.orchestrator_notes or "")]
    # Exactly one tirzepatide article in the whole plan, in the bigger silo
    # (more contributing keywords), and it carries keywords from BOTH silos.
    assert len(tirz_in_big) == 1
    assert len(tirz_in_small) == 0
    tirz = tirz_in_big[0]
    assert set([tirz.primary_keyword, *tirz.supporting_keywords]) == {
        "retatrutide vs tirzepatide",
        "retatrutide vs tirzepatide dosage",
        "switching from tirzepatide to retatrutide",
    }
    # The small silo keeps its non-peer parent article — the wipe-out is gone.
    assert any(a.primary_keyword == "kw b" for a in result.per_topic[1].articles)


def test_prefers_clean_vs_form_for_primary():
    """The peer article's primary should prefer the clean '{seed} vs {peer}' form
    if any keyword has it, otherwise the shortest."""
    result = _plan(_art(
        primary="something else",
        supporting=[
            "retatrutide vs tirzepatide weight loss outcome compared",
            "retatrutide vs tirzepatide",                         # clean vs form
            "switching from tirzepatide to retatrutide protocol",
        ],
    ))
    group_by_peer_entity(result, seed_terms=SEED, peer_terms=PEERS)
    tirz = next(a for a in result.per_topic[0].articles if a.intent == "comparison")
    assert tirz.primary_keyword == "retatrutide vs tirzepatide"


def test_multi_peer_keyword_forms_multi_peer_bucket():
    """`retatrutide vs tirzepatide vs semaglutide` mentions two peers -> its own
    multi-peer bucket, distinct from the single-peer buckets."""
    result = _plan(_art(
        primary="non peer primary",
        supporting=[
            "retatrutide vs tirzepatide",
            "retatrutide vs semaglutide",
            "retatrutide vs tirzepatide vs semaglutide",
        ],
    ))
    group_by_peer_entity(result, seed_terms=SEED, peer_terms=PEERS)

    comp = [a for a in result.per_topic[0].articles if a.intent == "comparison"]
    notes = [a.orchestrator_notes for a in comp]
    assert any(n == "Grouped by peer entity: tirzepatide" for n in notes)
    assert any(n == "Grouped by peer entity: semaglutide" for n in notes)
    assert any(n == "Grouped by peer entity: semaglutide, tirzepatide" for n in notes)
    assert len(comp) == 3


def test_single_keyword_naming_unique_peer_still_becomes_primary():
    """No minimum — even one keyword naming a peer with no other matches becomes
    its own article (zero supporting keywords is fine)."""
    result = _plan(_art(
        primary="retatrutide mechanism",
        supporting=["retatrutide vs zepbound"],
    ))
    group_by_peer_entity(result, seed_terms=SEED, peer_terms=PEERS)

    arts = _by_primary(result)
    assert "retatrutide vs zepbound" in arts
    assert arts["retatrutide vs zepbound"].supporting_keywords == []
    assert arts["retatrutide vs zepbound"].intent == "comparison"


def test_no_peer_entities_is_noop():
    """An empty peer_terms list (e.g. a seed with no peers) leaves the plan
    untouched."""
    before = [(a.primary_keyword, tuple(a.supporting_keywords))
              for a in [_art("p1", ["k1", "k2"])]]
    result = _plan(_art("p1", ["k1", "k2"]))
    group_by_peer_entity(result, seed_terms=SEED, peer_terms=[])
    after = [(a.primary_keyword, tuple(a.supporting_keywords))
             for a in result.per_topic[0].articles]
    assert before == after


def test_whole_word_match_substring_safe():
    """'redditor' contains 'reddit' but isn't a peer; 'tirzepatide-x' contains
    'tirzepatide' as a whole word and SHOULD match. Confirm whole-word semantics."""
    result = _plan(_art(
        primary="retatrutide guide",
        supporting=[
            "redditorial content review",   # not a peer (whole-word)
            "tirzepatide pricing tier",     # whole-word peer match
        ],
    ))
    # 'reddit' is not in PEERS — it would be filtered at the gate; here we just
    # confirm peer regex is whole-word for `tirzepatide`.
    group_by_peer_entity(result, seed_terms=SEED, peer_terms=PEERS)
    arts = _by_primary(result)
    # Parent keeps the non-peer redditorial keyword.
    assert "retatrutide guide" in arts
    assert "redditorial content review" in arts["retatrutide guide"].supporting_keywords
    # Tirzepatide article exists.
    assert "tirzepatide pricing tier" in arts


def test_promotes_non_peer_kw_to_primary_when_original_primary_was_peer_named():
    """Parent's primary was peer-named (moves to peer bucket); a non-peer kw is
    promoted to be the parent's new primary."""
    result = _plan(_art(
        primary="retatrutide vs tirzepatide",
        supporting=["retatrutide overview", "retatrutide background"],
    ))
    group_by_peer_entity(result, seed_terms=SEED, peer_terms=PEERS)

    arts = _by_primary(result)
    # Parent now has a non-peer primary, and the old peer-primary moved to the
    # tirzepatide article.
    assert "retatrutide vs tirzepatide" in arts
    tirz = arts["retatrutide vs tirzepatide"]
    assert tirz.intent == "comparison"
    # The promoted parent exists with one of the non-peer supporting as primary.
    parent = next(a for a in arts.values() if a.intent != "comparison")
    assert parent.primary_keyword in ("retatrutide overview", "retatrutide background")
    assert "promoted" in (parent.orchestrator_notes or "")
