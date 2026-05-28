"""Orphan keyword promotion (owner-requested follow-up to §7.10).

After every planning pass finishes (orchestrator -> peer-grouping -> split ->
dedup), some active keywords are silently NOT in any article — the orchestrator
chose to omit them (singletons, redundant long-tail) without formally dropping
them (no `orchestrator_drop_reason`), and cross-topic dedup loses the loser
article's supporting keywords. The user saw this with "what is retatrutide" —
a foundational query in the pool with relevance 0.72, not in any cluster.

On retatrutide this affected 44% of the active pool (679 of 1,541). This pass
catches every active keyword that ended up neither in an article nor formally
dropped and promotes it to its own singleton article (primary = the keyword,
supporting = []). Zero LLM / embedding cost — pure-compute set arithmetic.

Coverage is checked GLOBALLY (across all topics' articles), not per-topic, so
keywords pulled across silos by cross-topic peer-grouping are correctly
accounted for and don't get double-promoted.
"""

import logging

from .models import DEFAULT_INTENT, ArticleRecord, PlanResult, TopicInput

logger = logging.getLogger(__name__)


def promote_orphans(result: PlanResult, topics: list[TopicInput]) -> None:
    """Mutate `result` in place: every active keyword that isn't covered by an
    article (anywhere in the plan) and wasn't formally dropped becomes its own
    singleton article in its routed topic. Idempotent — re-running with the
    same input yields the same articles."""
    # Coverage is checked GLOBALLY so a keyword peer-grouped to a different
    # silo is still considered covered (not promoted again).
    covered: set[str] = set()
    dropped: set[str] = set()
    for plan in result.per_topic:
        for art in plan.articles:
            covered.add(art.primary_keyword)
            covered.update(art.supporting_keywords)
        for d in plan.dropped:
            dropped.add(d.keyword)

    topic_inputs_by_id = {t.id: t for t in topics}
    total_added = 0
    for plan in result.per_topic:
        topic_input = topic_inputs_by_id.get(plan.topic_id)
        if topic_input is None:
            continue
        # The topic's full active pool = union of all its Louvain groupings'
        # keywords (groupings are what the orchestrator received).
        all_active: set[str] = set()
        for g in topic_input.groupings:
            all_active.update(g.keywords)
        orphans = sorted(all_active - covered - dropped)
        if not orphans:
            continue
        for orphan in orphans:
            plan.articles.append(ArticleRecord(
                topic_id=plan.topic_id,
                primary_keyword=orphan,
                supporting_keywords=[],
                intent=DEFAULT_INTENT,
                suggested_h2s=[],
                source_statistical_grouping_id=None,
                orchestrator_notes="Promoted orphan: not assigned by the orchestrator.",
            ))
        plan.log["orphans_promoted"] = len(orphans)
        total_added += len(orphans)
        # Update the global covered set so a later topic-loop iteration doesn't
        # treat this topic's orphans as still-uncovered.
        covered.update(orphans)

    if total_added:
        logger.info(
            "step_complete",
            extra={"event": "step_complete", "step": "orphan_promotion",
                   "orphans_promoted": total_added},
        )
