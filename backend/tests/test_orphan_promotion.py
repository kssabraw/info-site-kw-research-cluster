"""Orphan keyword promotion — every active keyword the orchestrator silently
omitted becomes its own singleton article.

Pure unit tests: orphan detection, exclusion of formally-dropped keywords,
cross-topic coverage check (a keyword peer-grouped to another silo isn't
double-promoted), idempotence.
"""

from app.pipeline.article_planning.models import (
    ArticleRecord,
    DroppedKeyword,
    GroupingInput,
    PlanResult,
    TopicInput,
    TopicPlan,
)
from app.pipeline.article_planning.orphan_promotion import promote_orphans


def _topic(
    topic_id: str,
    keyword_groups: list[list[str]],
    relevance: dict[str, float] | None = None,
) -> TopicInput:
    """Build a TopicInput whose groupings cover the given keyword lists. Pass
    `relevance` to populate `keyword_relevance` for the min-score tests."""
    return TopicInput(
        id=topic_id, name=topic_id, rationale="", relationship_type="",
        embedding=None,
        groupings=[
            GroupingInput(
                id=f"{topic_id}:g{i}",
                representative=kws[0],
                cohesion=1.0, size=len(kws), keywords=list(kws),
            )
            for i, kws in enumerate(keyword_groups)
        ],
        keyword_relevance=relevance or {},
    )


def _article(primary: str, supporting: list[str], topic="t1") -> ArticleRecord:
    return ArticleRecord(
        topic_id=topic, primary_keyword=primary, supporting_keywords=supporting,
        intent="informational", suggested_h2s=[],
        source_statistical_grouping_id=None, orchestrator_notes="orig",
    )


def test_silently_omitted_keyword_becomes_its_own_article():
    """The owner-reported case: an active keyword in the gate output that's
    NOT in any article and was NOT formally dropped must be promoted."""
    topic = _topic("t1", [["retatrutide", "what is retatrutide", "what is retatrutide chemical name"]])
    result = PlanResult(per_topic=[TopicPlan(
        topic_id="t1",
        articles=[_article("retatrutide", [])],  # orchestrator only kept the rep
    )])

    promote_orphans(result, [topic])

    primaries = {a.primary_keyword for a in result.per_topic[0].articles}
    # The two silent orphans get their own articles; the original stays.
    assert primaries == {
        "retatrutide", "what is retatrutide", "what is retatrutide chemical name"
    }
    # Promoted articles are zero-supporting (the deliberate stub-article shape).
    promoted = [a for a in result.per_topic[0].articles
                if a.orchestrator_notes.startswith("Promoted orphan")]
    assert all(a.supporting_keywords == [] for a in promoted)
    assert result.per_topic[0].log["orphans_promoted"] == 2


def test_explicitly_dropped_keyword_is_not_promoted():
    """A keyword the orchestrator formally dropped (with a reason) is NOT
    silently lost — it goes to keywords.status='dropped_by_orchestrator' at
    persist. The promotion pass must leave it alone."""
    topic = _topic("t1", [["a", "b", "c"]])
    result = PlanResult(per_topic=[TopicPlan(
        topic_id="t1",
        articles=[_article("a", [])],
        dropped=[DroppedKeyword(keyword="b", reason="redundant")],
    )])

    promote_orphans(result, [topic])
    primaries = {a.primary_keyword for a in result.per_topic[0].articles}
    # 'a' was covered; 'b' was formally dropped; only 'c' is silently orphaned.
    assert primaries == {"a", "c"}


def test_keyword_covered_in_another_topic_is_not_promoted():
    """Cross-topic peer-grouping pulled a kw from topic A into a peer article
    in topic B. The kw is still covered (globally) — must not be re-promoted
    as a singleton in topic A."""
    topic_a = _topic("t_a", [["a1", "a2", "shared kw"]])
    topic_b = _topic("t_b", [["b1"]])
    result = PlanResult(per_topic=[
        TopicPlan(topic_id="t_a", articles=[_article("a1", ["a2"], topic="t_a")]),
        # peer-grouping moved 'shared kw' into a B-home article
        TopicPlan(topic_id="t_b", articles=[
            _article("b1", [], topic="t_b"),
            _article("shared kw", [], topic="t_b"),
        ]),
    ])

    promote_orphans(result, [topic_a, topic_b])
    a_primaries = {a.primary_keyword for a in result.per_topic[0].articles}
    # 'shared kw' is covered in topic_b — must NOT appear in topic_a.
    assert a_primaries == {"a1"}


def test_idempotent_second_run_is_a_noop():
    topic = _topic("t1", [["a", "b"]])
    result = PlanResult(per_topic=[TopicPlan(topic_id="t1", articles=[_article("a", [])])])
    promote_orphans(result, [topic])
    count_after_first = len(result.per_topic[0].articles)
    promote_orphans(result, [topic])
    assert len(result.per_topic[0].articles) == count_after_first


def test_topic_with_no_orphans_records_no_delta():
    topic = _topic("t1", [["a", "b"]])
    result = PlanResult(per_topic=[TopicPlan(
        topic_id="t1",
        articles=[_article("a", ["b"])],   # fully covered
    )])
    promote_orphans(result, [topic])
    assert len(result.per_topic[0].articles) == 1
    assert "orphans_promoted" not in result.per_topic[0].log


def test_min_score_keeps_strong_orphans_drops_marginal_ones():
    """At min_score=0.65, only orphans whose stored relevance >= 0.65 are
    promoted. The retatrutide distribution: 'what is retatrutide' (0.72)
    promoted; 'random marginal kw' (0.55) stays as a bare-active orphan."""
    topic = _topic(
        "t1",
        [["retatrutide", "what is retatrutide", "marginal kw", "edge kw"]],
        relevance={"retatrutide": 0.85, "what is retatrutide": 0.72,
                   "marginal kw": 0.55, "edge kw": 0.649},
    )
    result = PlanResult(per_topic=[TopicPlan(
        topic_id="t1",
        articles=[_article("retatrutide", [])],
    )])

    promote_orphans(result, [topic], min_score=0.65)
    primaries = {a.primary_keyword for a in result.per_topic[0].articles}
    # 0.72 promoted; 0.55 and 0.649 (just below the floor) stay orphaned.
    assert primaries == {"retatrutide", "what is retatrutide"}
    assert result.per_topic[0].log["orphans_promoted"] == 1
    assert result.per_topic[0].log["orphans_below_floor"] == 2


def test_min_score_keyword_with_missing_score_is_not_promoted():
    """Defensive: an orphan without a recorded score (shouldn't happen if
    the caller populates `keyword_relevance` correctly) is treated as below
    the floor — better to leave it orphaned than promote a possibly-junk kw."""
    topic = _topic("t1", [["a", "b", "c"]], relevance={"a": 0.9, "b": 0.9})
    # 'c' has no score recorded.
    result = PlanResult(per_topic=[TopicPlan(
        topic_id="t1", articles=[_article("a", [])],
    )])
    promote_orphans(result, [topic], min_score=0.65)
    primaries = {a.primary_keyword for a in result.per_topic[0].articles}
    assert primaries == {"a", "b"}     # 'c' (no score) is not promoted


def test_min_score_zero_promotes_everything_legacy_behavior():
    """The default min_score=0 path is a no-op floor (used by tests that
    don't care about the quality bar)."""
    topic = _topic("t1", [["a", "b"]])   # no relevance map needed
    result = PlanResult(per_topic=[TopicPlan(
        topic_id="t1", articles=[_article("a", [])],
    )])
    promote_orphans(result, [topic])   # default min_score=0
    primaries = {a.primary_keyword for a in result.per_topic[0].articles}
    assert primaries == {"a", "b"}
