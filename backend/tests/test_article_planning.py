"""M5 article planning tests (PRD §7.10): per-topic orchestrator, validation,
degraded fallback, cross-topic dedup, and the candidate-SERP fetch."""

from app.llm import AnthropicError
from app.pipeline.article_planning.dedup import cross_topic_dedup
from app.pipeline.article_planning.models import (
    ArticleRecord,
    GroupingInput,
    PlanResult,
    TopicInput,
    TopicPlan,
)
from app.pipeline.article_planning.orchestrate_articles import (
    all_degraded,
    plan_topic,
    run_article_planning,
)
from app.pipeline.article_planning.serp import fetch_candidate_serps


class FakeOrchestrator:
    """Returns a preset tool payload, or raises to exercise reprompt/degrade."""

    def __init__(self, payload=None, raises=False):
        self.payload = payload
        self.raises = raises
        self.calls = 0

    def call_tool(self, **kwargs):
        self.calls += 1
        if self.raises:
            raise AnthropicError("boom")
        return self.payload


def _topic():
    return TopicInput(
        id="t1",
        name="Benefits",
        rationale="why",
        relationship_type="effect_or_outcome",
        embedding=[1.0, 0.0],
        groupings=[
            GroupingInput(
                id="t1:g0",
                representative="retatrutide weight loss",
                cohesion=0.8,
                size=3,
                keywords=[
                    "retatrutide weight loss",
                    "retatrutide weight loss results",
                    "how much weight on retatrutide",
                ],
            )
        ],
    )


def test_plan_topic_builds_articles_from_pool():
    payload = {
        "articles": [
            {
                "primary_keyword": "Retatrutide Weight Loss",  # case-insensitive match
                "supporting_keywords": [
                    "retatrutide weight loss results",
                    "not in pool",  # discarded
                ],
                "intent": "informational",
                "suggested_h2s": ["How it works", "Expected results"],
                "source_statistical_grouping_id": "t1:g0",
                "orchestrator_notes": "merged",
            }
        ],
        "dropped_keywords": [
            {"keyword": "how much weight on retatrutide", "reason": "no traction"}
        ],
        "coverage_gaps": [
            {"suggested_title": "Long-term safety", "target_keyword": "retatrutide long term",
             "rationale": "authority"}
        ],
    }
    serp = {"retatrutide weight loss": ["https://a.com", "https://b.com"]}
    plan = plan_topic(_topic(), serp, FakeOrchestrator(payload))

    assert len(plan.articles) == 1
    art = plan.articles[0]
    assert art.primary_keyword == "retatrutide weight loss"  # resolved to pool form
    assert art.supporting_keywords == ["retatrutide weight loss results"]
    assert art.intent == "informational"
    assert art.serp_top_urls == ["https://a.com", "https://b.com"]
    assert [d.keyword for d in plan.dropped] == ["how much weight on retatrutide"]
    assert plan.gaps[0].suggested_title == "Long-term safety"
    assert plan.degraded is False


def test_plan_topic_skips_article_without_supporting_keywords():
    payload = {
        "articles": [
            {
                "primary_keyword": "retatrutide weight loss",
                "supporting_keywords": [],  # no companions -> not a cluster
                "intent": "informational",
                "suggested_h2s": [],
                "orchestrator_notes": "",
            }
        ],
        "dropped_keywords": [],
        "coverage_gaps": [],
    }
    plan = plan_topic(_topic(), {}, FakeOrchestrator(payload))
    assert plan.articles == []
    assert any(s["why"] == "no supporting keywords" for s in plan.log["skipped_items"])


def test_plan_topic_coerces_bad_intent_and_drops_unknown_primary():
    payload = {
        "articles": [
            {
                "primary_keyword": "totally invented keyword",  # not in pool -> dropped
                "supporting_keywords": ["retatrutide weight loss"],
                "intent": "informational",
                "suggested_h2s": [],
                "orchestrator_notes": "",
            },
            {
                "primary_keyword": "retatrutide weight loss",
                "supporting_keywords": ["retatrutide weight loss results"],
                "intent": "nonsense-intent",  # coerced to default
                "suggested_h2s": [],
                "orchestrator_notes": "",
            },
        ],
        "dropped_keywords": [],
        "coverage_gaps": [],
    }
    plan = plan_topic(_topic(), {}, FakeOrchestrator(payload))
    assert len(plan.articles) == 1
    assert plan.articles[0].intent == "informational"


def test_plan_topic_reprompts_once_then_degrades():
    orch = FakeOrchestrator(raises=True)
    plan = plan_topic(_topic(), {}, orch)
    assert orch.calls == 2  # one reprompt
    assert plan.degraded is True
    # passthrough: the one grouping (3 keywords) becomes one article.
    assert len(plan.articles) == 1
    assert plan.articles[0].primary_keyword == "retatrutide weight loss"
    assert len(plan.articles[0].supporting_keywords) == 2


def test_all_degraded():
    degraded = TopicPlan(topic_id="t1", degraded=True)
    ok = TopicPlan(topic_id="t2", degraded=False)
    empty = TopicPlan(topic_id="t3", log={"note": "no groupings"})
    assert all_degraded(PlanResult(per_topic=[degraded])) is True
    assert all_degraded(PlanResult(per_topic=[degraded, ok])) is False
    # a "no groupings" topic doesn't count against the degrade check
    assert all_degraded(PlanResult(per_topic=[degraded, empty])) is True


def _article(topic_id, primary, serp=None):
    return ArticleRecord(
        topic_id=topic_id,
        primary_keyword=primary,
        supporting_keywords=["x"],
        intent="informational",
        suggested_h2s=[],
        source_statistical_grouping_id=None,
        orchestrator_notes="",
        serp_top_urls=serp or [],
    )


def test_cross_topic_dedup_cosine_collision_drops_loser_and_links():
    a1 = _article("A", "p")
    b1 = _article("B", "p2")     # identical embedding to p -> collision
    b2 = _article("B", "other")  # distinct -> survives, carries the peer link
    result = PlanResult(per_topic=[
        TopicPlan(topic_id="A", articles=[a1]),
        TopicPlan(topic_id="B", articles=[b1, b2]),
    ])
    vecs = {"p": [1.0, 0.0], "p2": [1.0, 0.0], "other": [0.0, 1.0]}

    cross_topic_dedup(
        result,
        topic_embeddings={"A": [1.0, 0.0], "B": [1.0, 0.0]},
        embed_fn=lambda kws: [vecs[k] for k in kws],
    )

    a_articles = [a.primary_keyword for p in result.per_topic if p.topic_id == "A" for a in p.articles]
    b_articles = [a.primary_keyword for p in result.per_topic if p.topic_id == "B" for a in p.articles]
    assert a_articles == ["p"]            # winner kept
    assert b_articles == ["other"]        # loser p2 dropped, survivor stays
    assert len(result.dedup_log["collisions"]) == 1
    # losing topic's survivor links to the winner, and vice versa
    assert "p" in b2.peer_primary_keywords
    assert "other" in a1.peer_primary_keywords


def test_cross_topic_dedup_serp_overlap_collision():
    shared = ["https://x.com/1", "https://x.com/2", "https://x.com/3"]
    a1 = _article("A", "alpha", serp=shared)
    b1 = _article("B", "beta", serp=shared)  # same top-3 -> overlap collision
    result = PlanResult(per_topic=[
        TopicPlan(topic_id="A", articles=[a1]),
        TopicPlan(topic_id="B", articles=[b1]),
    ])
    # Orthogonal embeddings so only the SERP-overlap rule can fire.
    vecs = {"alpha": [1.0, 0.0], "beta": [0.0, 1.0]}
    cross_topic_dedup(
        result,
        topic_embeddings={"A": [1.0, 0.0], "B": [0.0, 1.0]},
        embed_fn=lambda kws: [vecs[k] for k in kws],
    )
    assert len(result.dedup_log["collisions"]) == 1
    assert result.dedup_log["dropped"] == 1


class _SerpDFS:
    def serp_top_urls(self, keyword, top_n=10):
        if keyword == "boom":
            raise RuntimeError("serp down")
        return [f"https://{keyword}.com/{i}" for i in range(top_n)]


def test_fetch_candidate_serps_degrades_per_keyword():
    res = fetch_candidate_serps(
        keywords=["ok", "boom", "ok"],  # duplicate deduped
        dfs=_SerpDFS(),
    )
    assert "ok" in res.per_keyword
    assert "boom" not in res.per_keyword
    assert len(res.degraded_notes) == 1


def test_run_article_planning_end_to_end_with_fakes():
    topics = [_topic()]
    payload = {
        "articles": [
            {
                "primary_keyword": "retatrutide weight loss",
                "supporting_keywords": ["retatrutide weight loss results"],
                "intent": "informational",
                "suggested_h2s": ["a"],
                "orchestrator_notes": "ok",
            }
        ],
        "dropped_keywords": [],
        "coverage_gaps": [],
    }
    result = run_article_planning(
        topics=topics,
        dfs=_SerpDFS(),
        orchestrator=FakeOrchestrator(payload),
        embed_fn=lambda kws: [[1.0, 0.0] for _ in kws],
    )
    assert result.counts()["articles"] == 1
    assert all_degraded(result) is False
