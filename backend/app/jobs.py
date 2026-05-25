"""Background execution for the long pipeline operations.

`/expand`, `/plan-articles`, and `/regate` exceed Railway's ~5-min edge cap when
run inside the request, so the endpoints claim the run (atomic status flip),
submit the work here, and return 202 immediately. The frontend polls session
status. Each job owns its terminal status: it sets `awaiting_article_planning` /
`complete` on success, or `error` + `last_error` on failure.

A bounded pool caps concurrent pipeline runs per process; the per-session run
guard (try_mark_running) prevents the same session running twice. Jobs use the
service client (no user token — the request already authorized the caller).

Caveat (accepted for v1, real fix = a durable queue): a process restart mid-job
strands the session at status='running'. Recovery is a new session until M7's
resume lands.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from app.config import get_settings
from app.dataforseo import get_dataforseo
from app.llm import get_llm, get_orchestrator
from app.logging import bind_session_id
from app.pipeline.article_planning.models import GroupingInput, TopicInput
from app.pipeline.article_planning.orchestrate_articles import (
    all_degraded,
    run_article_planning,
)
from app.pipeline.orchestrate import (
    PipelineTopic,
    gate_and_cluster,
    run_refinement_pipeline,
)
from app.storage import silo as store

logger = logging.getLogger(__name__)

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pipeline")


def _short(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:500]


def submit_expand(session_id: str) -> None:
    _EXECUTOR.submit(run_expand_job, session_id)


def submit_plan(session_id: str, direct: bool = False) -> None:
    _EXECUTOR.submit(run_plan_job, session_id, direct)


def submit_regate(
    session_id: str,
    threshold: float,
    edge_threshold: float,
    resolution: float,
    seed_terms: list[str],
    peer_terms: list[str],
) -> None:
    _EXECUTOR.submit(run_regate_job, session_id, threshold, edge_threshold,
                     resolution, seed_terms, peer_terms)


def run_expand_job(session_id: str) -> None:
    """§7.3–§7.9: expansion + competitor mining + relevance gate + clustering."""
    bind_session_id(session_id)
    try:
        session = store.get_session(session_id)
        topics = store.list_topics(session_id)
        embeddings = store.get_topic_embeddings(session_id)
        s = get_settings()
        coverage_mode = (session.get("settings") or {}).get("coverage_mode", "standard")
        top_n = (
            s.competitor_top_n_comprehensive
            if coverage_mode == "comprehensive"
            else s.competitor_top_n_standard
        )
        seed = session["seed_keyword"]
        result = run_refinement_pipeline(
            seed=seed,
            topics=[
                PipelineTopic(
                    id=t["id"],
                    name=t["name"],
                    embedding=embeddings.get(t["id"]),
                    gated=bool(t.get("is_gated_for_competitor_mining")),
                )
                for t in topics
            ],
            dfs=get_dataforseo(),
            embed_fn=get_llm().embed,
            seed_terms=[seed, *(session.get("aliases") or [])],
            peer_terms=session.get("peer_entities") or [],
            keyword_ideas_limit=s.keyword_ideas_limit,
            keyword_suggestions_limit=s.keyword_suggestions_limit,
            query_fanouts_limit=s.query_fanouts_limit,
            paa_tier1_seeds=s.paa_tier1_seeds,
            paa_tier2_cap=s.paa_tier2_cap,
            autocomplete_max=s.autocomplete_max,
            expansion_max_workers=s.expansion_max_workers,
            expansion_time_budget_s=s.expansion_time_budget_s,
            competitor_top_n=top_n,
            ranked_keywords_limit=s.ranked_keywords_limit,
            competitor_max_position=s.competitor_max_position,
            competitor_max_workers=s.competitor_max_workers,
            competitor_time_budget_s=s.competitor_time_budget_s,
            relevance_threshold=s.relevance_threshold,
            relevance_embed_batch=s.relevance_embed_batch,
            clustering_edge_threshold=s.clustering_edge_threshold,
            clustering_resolution=s.clustering_resolution,
            clustering_max_nodes=s.clustering_max_nodes,
        )
        store.delete_keywords_for_session(session_id)
        store.insert_classified_keywords(session_id, result.per_topic_gated)
        store.update_session(
            session_id,
            {
                "statistical_clustering_log": result.clustering_log,
                "status": "awaiting_article_planning",
            },
        )
        logger.info(
            "step_complete",
            extra={"event": "step_complete", "step": "expand_job", **result.counts()},
        )
    except Exception as exc:  # noqa: BLE001 — terminal status carries the failure
        logger.error(
            "step_failed",
            extra={"event": "step_failed", "step": "expand_job", "reason": repr(exc)},
        )
        store.update_session(session_id, {"status": "error", "last_error": _short(exc)})


def run_plan_job(session_id: str, direct: bool = False) -> None:
    """§7.10: SERP for candidate primaries + per-silo orchestrator + dedup.
    With direct=True, skips the orchestrator (groupings -> articles + dedup)."""
    bind_session_id(session_id)
    try:
        session = store.get_session(session_id)
        log_topics = (session.get("statistical_clustering_log") or {}).get("topics") or {}
        topics_meta = {t["id"]: t for t in store.list_topics(session_id)}
        embeddings = store.get_topic_embeddings(session_id)
        topic_inputs = [
            TopicInput(
                id=tid,
                name=meta.get("name") or "",
                rationale=meta.get("rationale") or "",
                relationship_type=meta.get("relationship_type") or "",
                embedding=embeddings.get(tid),
                groupings=[
                    GroupingInput(
                        id=str(g.get("id") or f"{tid}:g{i}"),
                        representative=str(g.get("representative") or ""),
                        cohesion=float(g.get("cohesion") or 0.0),
                        size=int(g.get("size") or len(g.get("keywords") or [])),
                        keywords=[str(k) for k in (g.get("keywords") or [])],
                    )
                    for i, g in enumerate((log_topics.get(tid) or {}).get("groupings") or [])
                ],
            )
            for tid, meta in topics_meta.items()
        ]
        s = get_settings()
        result = run_article_planning(
            topics=topic_inputs,
            dfs=get_dataforseo(),
            orchestrator=get_orchestrator(),
            embed_fn=get_llm().embed,
            candidate_serp_top_n=s.candidate_serp_top_n,
            candidate_serp_max_workers=s.candidate_serp_max_workers,
            candidate_serp_time_budget_s=s.candidate_serp_time_budget_s,
            groupings_per_call=s.orchestrator_groupings_per_call,
            max_workers=s.orchestrator_max_workers,
            dedup_primary_cosine_threshold=s.dedup_primary_cosine_threshold,
            dedup_serp_overlap_min=s.dedup_serp_overlap_min,
            direct=direct,
        )
        if all_degraded(result):
            # Clear any stale prior plan so an errored run doesn't leave clusters
            # behind that disagree with status=error (review M5).
            store.reset_article_planning(session_id)
            store.update_session(
                session_id,
                {
                    "status": "error",
                    "orchestrator_log": result.orchestrator_log(),
                    "last_error": "Article planning failed on every silo "
                    "(orchestrator unavailable). Statistical clustering preserved.",
                },
            )
            return
        store.reset_article_planning(session_id)
        store.persist_article_plan(session_id, result, get_llm().embed)
        store.update_session(
            session_id,
            {"orchestrator_log": result.orchestrator_log(), "status": "complete"},
        )
        logger.info(
            "step_complete",
            extra={"event": "step_complete", "step": "plan_job", **result.counts()},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "step_failed",
            extra={"event": "step_failed", "step": "plan_job", "reason": repr(exc)},
        )
        store.update_session(session_id, {"status": "error", "last_error": _short(exc)})


def run_regate_job(
    session_id: str, threshold: float, edge_threshold: float, resolution: float,
    seed_terms: list[str], peer_terms: list[str],
) -> None:
    """Re-gate + re-cluster a session's stored keyword pool at a new threshold and
    clustering granularity, skipping DataForSEO. Clears any prior article plan."""
    bind_session_id(session_id)
    try:
        pool = store.list_all_keyword_pool(session_id)
        topics = store.list_topics(session_id)
        topic_names = {t["id"]: t["name"] for t in topics}
        topic_embeddings = store.get_topic_embeddings(session_id)
        s = get_settings()
        gc = gate_and_cluster(
            per_topic_lists=pool,
            topic_names=topic_names,
            topic_embeddings=topic_embeddings,
            embed_fn=get_llm().embed,
            relevance_threshold=threshold,
            relevance_embed_batch=s.relevance_embed_batch,
            clustering_edge_threshold=edge_threshold,
            clustering_resolution=resolution,
            clustering_max_nodes=s.clustering_max_nodes,
            seed_terms=seed_terms,
            peer_terms=peer_terms,
        )
        store.reset_article_planning(session_id)
        store.delete_keywords_for_session(session_id)
        store.insert_classified_keywords(session_id, gc.per_topic_gated)
        store.update_session(
            session_id,
            {
                "statistical_clustering_log": gc.clustering_log,
                "orchestrator_log": None,
                "status": "awaiting_article_planning",
            },
        )
        logger.info(
            "step_complete",
            extra={"event": "step_complete", "step": "regate_job",
                   "threshold": threshold, **gc.counts()},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "step_failed",
            extra={"event": "step_failed", "step": "regate_job", "reason": repr(exc)},
        )
        store.update_session(session_id, {"status": "error", "last_error": _short(exc)})
