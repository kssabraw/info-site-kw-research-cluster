"""Storage operations for sessions and topics (M2 silo discovery).

Reads that serve a user and ownership checks go through the user-scoped client
so RLS enforces visibility. Writes the backend orchestrates go through the
service client after ownership has been verified.
"""

import json

from app.pipeline.article_planning.models import PlanResult
from app.pipeline.models import ProposedSilo
from app.pipeline.relevance import GatedKeyword
from app.storage.supabase_client import (
    ensure_scratch_project,
    get_service_client,
    get_user_client,
)


def _norm(kw: str) -> str:
    return " ".join((kw or "").strip().lower().split())


def _vector_literal(vector: list[float]) -> str:
    # pgvector accepts its text form "[a,b,c]".
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"

# Columns returned to the API — never the raw embedding vector.
_TOPIC_COLS = (
    "id, session_id, name, rationale, relationship_type, supporting_evidence, "
    "source, is_broader_class, is_gated_for_competitor_mining, created_at"
)


def project_visible_to_user(access_token: str, project_id: str) -> bool:
    """True if RLS lets this user see the project (i.e. they may attach a
    session to it). Prevents attaching a session to a project the caller does
    not own (PRD §13: INSERTs gated by the same scope)."""
    res = (
        get_user_client(access_token)
        .table("projects")
        .select("id")
        .eq("id", project_id)
        .limit(1)
        .execute()
    )
    return bool(res.data)


def resolve_project_id(user_id: str, project_id: str | None) -> str:
    if project_id:
        return project_id
    return ensure_scratch_project(user_id)["id"]


def create_session(
    *,
    user_id: str,
    project_id: str,
    seed_keyword: str,
    audience_hint: str | None,
    disambiguation_hint: str | None,
    settings: dict,
) -> dict:
    row = (
        get_service_client()
        .table("sessions")
        .insert(
            {
                "user_id": user_id,
                "project_id": project_id,
                "seed_keyword": seed_keyword,
                "audience_hint": audience_hint,
                "disambiguation_hint": disambiguation_hint,
                "settings": settings,
                "status": "running_pre_review",
            }
        )
        .execute()
    )
    return row.data[0]


def session_visible_to_user(access_token: str, session_id: str) -> dict | None:
    """Return the session if RLS lets this user see it, else None."""
    res = (
        get_user_client(access_token)
        .table("sessions")
        .select("*")
        .eq("id", session_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def update_session(session_id: str, fields: dict) -> dict:
    row = (
        get_service_client()
        .table("sessions")
        .update(fields)
        .eq("id", session_id)
        .execute()
    )
    return row.data[0]


def try_mark_running(session_id: str) -> bool:
    """Atomically claim a session for a pipeline run: set status='running' only
    if it isn't already running. Returns True if this caller acquired the run,
    False if a run was already in progress. The `neq` makes the check-and-set a
    single guarded UPDATE, so two concurrent callers can't both proceed
    (prevents duplicate rows + double API spend on a double-submit/retry).
    Clears any stale last_error from a prior failed run."""
    res = (
        get_service_client()
        .table("sessions")
        .update({"status": "running", "last_error": None})
        .eq("id", session_id)
        .neq("status", "running")
        .execute()
    )
    return bool(res.data)


def get_session(session_id: str) -> dict | None:
    """Service-side session fetch (no RLS), for background jobs that run after the
    request has returned and have no user token."""
    res = (
        get_service_client()
        .table("sessions")
        .select("*")
        .eq("id", session_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def delete_topics_for_session(session_id: str) -> None:
    get_service_client().table("topics").delete().eq("session_id", session_id).execute()


def insert_proposed_topics(session_id: str, silos: list[ProposedSilo]) -> list[dict]:
    if not silos:
        return []
    payload = [
        {
            "session_id": session_id,
            "name": s.name,
            "rationale": s.rationale,
            "relationship_type": s.relationship_type.value,
            "supporting_evidence": s.supporting_evidence,
            "source": "llm_proposed",
            "is_broader_class": s.is_broader_class,
        }
        for s in silos
    ]
    res = get_service_client().table("topics").insert(payload).execute()
    return res.data


def list_topics(session_id: str) -> list[dict]:
    res = (
        get_service_client()
        .table("topics")
        .select(_TOPIC_COLS)
        .eq("session_id", session_id)
        .order("created_at")
        .order("id")
        .execute()
    )
    return res.data


def insert_custom_topic(
    session_id: str,
    *,
    name: str,
    rationale: str | None,
    relationship_type: str,
    is_broader_class: bool,
) -> dict:
    res = (
        get_service_client()
        .table("topics")
        .insert(
            {
                "session_id": session_id,
                "name": name,
                "rationale": rationale,
                "relationship_type": relationship_type,
                "source": "user_added",
                "is_broader_class": is_broader_class,
            }
        )
        .execute()
    )
    # Re-fetch with the restricted column set so the embedding is never returned.
    return get_topic(res.data[0]["id"])


def get_topic(topic_id: str) -> dict | None:
    res = (
        get_service_client()
        .table("topics")
        .select(_TOPIC_COLS)
        .eq("id", topic_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def update_topic(topic_id: str, fields: dict) -> dict:
    get_service_client().table("topics").update(fields).eq("id", topic_id).execute()
    # Re-fetch with the restricted column set so the embedding is never returned.
    return get_topic(topic_id)


def delete_topic(topic_id: str) -> None:
    get_service_client().table("topics").delete().eq("id", topic_id).execute()


# ---- M3 keyword expansion -------------------------------------------------
_KEYWORD_COLS = (
    "id, topic_id, cluster_id, keyword, sources, status, relevance_score, "
    "is_primary_for_cluster, orchestrator_drop_reason, created_at"
)


def delete_keywords_for_session(session_id: str) -> None:
    get_service_client().table("keywords").delete().eq("session_id", session_id).execute()


def insert_keywords(session_id: str, per_topic: dict[str, dict[str, list[str]]]) -> int:
    rows = [
        {"session_id": session_id, "topic_id": tid, "keyword": kw, "sources": sources}
        for tid, kws in per_topic.items()
        for kw, sources in kws.items()
    ]
    client = get_service_client()
    for start in range(0, len(rows), 500):
        client.table("keywords").insert(rows[start : start + 500]).execute()
    return len(rows)


def list_keywords(
    session_id: str,
    topic_id: str | None = None,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    q = (
        get_service_client()
        .table("keywords")
        .select(_KEYWORD_COLS)
        .eq("session_id", session_id)
    )
    if topic_id:
        q = q.eq("topic_id", topic_id)
    if status:
        q = q.eq("status", status)
    res = q.order("created_at").range(offset, offset + limit - 1).execute()
    return res.data


# ---- M4 deep-mine gating, relevance, clustering ---------------------------
def set_topics_gating(session_id: str, gated_topic_ids: list[str]) -> None:
    """Mark which silos are gated for competitor mining (PRD §7.2). Clears the
    flag on all of the session's topics, then sets it on the selected ones."""
    client = get_service_client()
    client.table("topics").update({"is_gated_for_competitor_mining": False}).eq(
        "session_id", session_id
    ).execute()
    if gated_topic_ids:
        client.table("topics").update({"is_gated_for_competitor_mining": True}).eq(
            "session_id", session_id
        ).in_("id", gated_topic_ids).execute()


def get_topic_embeddings(session_id: str) -> dict[str, list[float] | None]:
    """topic_id -> embedding vector (parsed from pgvector's text form), for the
    relevance gate. Never exposed through the API."""
    res = (
        get_service_client()
        .table("topics")
        .select("id, embedding")
        .eq("session_id", session_id)
        .execute()
    )
    out: dict[str, list[float] | None] = {}
    for row in res.data:
        emb = row.get("embedding")
        if isinstance(emb, str):
            try:
                emb = json.loads(emb)
            except (ValueError, TypeError):
                emb = None
        out[row["id"]] = emb
    return out


def list_all_keyword_pool(session_id: str) -> dict[str, dict[str, list[str]]]:
    """Reconstruct the pre-gate candidate pool (topic_id -> {keyword: sources})
    from every stored keyword row, regardless of current status. Used by the
    re-gate path to re-run the relevance gate + clustering on the already-
    collected keywords without re-hitting DataForSEO. Paged for large pools."""
    client = get_service_client()
    pool: dict[str, dict[str, list[str]]] = {}
    offset = 0
    page = 1000
    while True:
        res = (
            client.table("keywords")
            .select("topic_id, keyword, sources")
            .eq("session_id", session_id)
            .order("id")
            .range(offset, offset + page - 1)
            .execute()
        )
        rows = res.data or []
        for r in rows:
            pool.setdefault(r["topic_id"], {})[r["keyword"]] = r.get("sources") or []
        if len(rows) < page:
            break
        offset += page
    return pool


def insert_classified_keywords(
    session_id: str, per_topic: dict[str, list[GatedKeyword]]
) -> int:
    """Persist gate output: every keyword with its status (active /
    filtered_relevance / filtered_junk) and relevance_score. Nothing is dropped."""
    rows = [
        {
            "session_id": session_id,
            "topic_id": tid,
            "keyword": g.keyword,
            "sources": g.sources,
            "status": g.status,
            "relevance_score": g.relevance_score,
        }
        for tid, kws in per_topic.items()
        for g in kws
    ]
    client = get_service_client()
    for start in range(0, len(rows), 500):
        client.table("keywords").insert(rows[start : start + 500]).execute()
    return len(rows)


def set_topic_embedding(topic_id: str, vector: list[float]) -> None:
    get_service_client().table("topics").update(
        {"embedding": _vector_literal(vector)}
    ).eq("id", topic_id).execute()


# ---- M5 article planning persistence (PRD §7.10, §13) ---------------------
def get_active_keyword_index(session_id: str) -> dict[tuple[str, str], str]:
    """(topic_id, normalized keyword) -> keyword row id, for the session's active
    keywords (the only pool the orchestrator saw). Paged: a broad silo can hold
    well over PostgREST's 1000-row default."""
    client = get_service_client()
    index: dict[tuple[str, str], str] = {}
    offset = 0
    page = 1000
    while True:
        res = (
            client.table("keywords")
            .select("id, topic_id, keyword")
            .eq("session_id", session_id)
            .eq("status", "active")
            .order("id")
            .range(offset, offset + page - 1)
            .execute()
        )
        rows = res.data or []
        for r in rows:
            index[(r["topic_id"], _norm(r["keyword"]))] = r["id"]
        if len(rows) < page:
            break
        offset += page
    return index


def reset_article_planning(session_id: str) -> None:
    """Clear any prior article-planning output so /plan-articles is idempotent
    (and re-runnable). Resets keyword orchestrator fields, un-drops
    orchestrator-dropped keywords, and deletes clusters + coverage gaps."""
    client = get_service_client()
    # Un-drop keywords the orchestrator dropped on a previous run.
    client.table("keywords").update({"status": "active"}).eq(
        "session_id", session_id
    ).eq("status", "dropped_by_orchestrator").execute()
    # Clear per-keyword cluster linkage.
    client.table("keywords").update(
        {
            "cluster_id": None,
            "is_primary_for_cluster": False,
            "serp_top_urls": None,
            "orchestrator_drop_reason": None,
        }
    ).eq("session_id", session_id).execute()

    topic_ids = [t["id"] for t in list_topics(session_id)]
    if topic_ids:
        client.table("coverage_gaps").delete().in_("topic_id", topic_ids).execute()
        client.table("clusters").delete().in_("topic_id", topic_ids).execute()


def persist_article_plan(session_id: str, result: PlanResult, embed_fn) -> dict:
    """Write the orchestrator's plan: clusters, keyword linkage, dropped keywords,
    peer links, coverage gaps. Handles the clusters<->keywords FK cycle with a
    staged write (insert clusters -> link keywords -> backfill primary + peers).
    Returns counts."""
    client = get_service_client()
    kw_index = get_active_keyword_index(session_id)

    # 1) Insert a cluster per article; remember the row id and keyword linkage.
    articles = [(p.topic_id, a) for p in result.per_topic for a in p.articles]
    cluster_ids: list[str] = []
    primary_to_cluster: dict[str, str] = {}      # norm(primary) -> cluster id
    per_cluster_primary_kw_id: list[str | None] = []
    per_cluster_serp: list[list[str]] = []
    per_cluster_supporting_kw_ids: list[list[str]] = []

    for topic_id, art in articles:
        row = (
            client.table("clusters")
            .insert(
                {
                    "topic_id": topic_id,
                    "name": art.primary_keyword,
                    "intent": art.intent,
                    "suggested_h2s": art.suggested_h2s,
                    "source_statistical_grouping_id": art.source_statistical_grouping_id,
                    "orchestrator_notes": art.orchestrator_notes,
                    "is_gap_placeholder": False,
                }
            )
            .execute()
        )
        cid = row.data[0]["id"]
        cluster_ids.append(cid)
        primary_to_cluster[_norm(art.primary_keyword)] = cid
        per_cluster_primary_kw_id.append(kw_index.get((topic_id, _norm(art.primary_keyword))))
        per_cluster_serp.append(art.serp_top_urls or [])
        per_cluster_supporting_kw_ids.append(
            [kid for sk in art.supporting_keywords
             if (kid := kw_index.get((topic_id, _norm(sk)))) is not None]
        )

    # 2) Link keywords to clusters and backfill each cluster's primary + peers.
    primary_embeddings = embed_fn([art.primary_keyword for _, art in articles]) if articles else []
    for idx, (cid, (topic_id, art)) in enumerate(zip(cluster_ids, articles)):
        primary_kw_id = per_cluster_primary_kw_id[idx]
        update: dict = {}
        if primary_kw_id:
            client.table("keywords").update(
                {
                    "cluster_id": cid,
                    "is_primary_for_cluster": True,
                    "serp_top_urls": per_cluster_serp[idx] or None,
                }
            ).eq("id", primary_kw_id).execute()
            update["primary_keyword_id"] = primary_kw_id
        support_ids = per_cluster_supporting_kw_ids[idx]
        if support_ids:
            client.table("keywords").update({"cluster_id": cid}).in_(
                "id", support_ids
            ).execute()
        peer_ids = [
            primary_to_cluster[_norm(pk)]
            for pk in art.peer_primary_keywords
            if _norm(pk) in primary_to_cluster
            and primary_to_cluster[_norm(pk)] != cid
        ]
        if peer_ids:
            update["peer_article_links"] = list(dict.fromkeys(peer_ids))
        if idx < len(primary_embeddings):
            update["centroid_embedding"] = _vector_literal(primary_embeddings[idx])
        if update:
            client.table("clusters").update(update).eq("id", cid).execute()

    # 3) Drop keywords the orchestrator dropped (stored, not deleted).
    dropped = 0
    for plan in result.per_topic:
        for d in plan.dropped:
            kid = kw_index.get((plan.topic_id, _norm(d.keyword)))
            if not kid:
                continue
            client.table("keywords").update(
                {"status": "dropped_by_orchestrator", "orchestrator_drop_reason": d.reason}
            ).eq("id", kid).execute()
            dropped += 1

    # 4) Coverage gaps (pending; acceptance -> placeholder cluster is M7).
    gap_rows = [
        {
            "topic_id": plan.topic_id,
            "suggested_title": g.suggested_title,
            "target_keyword": g.target_keyword,
            "rationale": g.rationale,
        }
        for plan in result.per_topic
        for g in plan.gaps
    ]
    if gap_rows:
        client.table("coverage_gaps").insert(gap_rows).execute()

    return {"clusters": len(cluster_ids), "dropped": dropped, "gaps": len(gap_rows)}


def list_clusters(session_id: str) -> list[dict]:
    """Article units for a session, joined up through topics. Read-only summary
    (full editing UI is M7); never returns the centroid embedding."""
    topic_ids = [t["id"] for t in list_topics(session_id)]
    if not topic_ids:
        return []
    res = (
        get_service_client()
        .table("clusters")
        .select(
            "id, topic_id, name, primary_keyword_id, intent, suggested_h2s, "
            "peer_article_links, source_statistical_grouping_id, orchestrator_notes, "
            "is_user_edited, is_gap_placeholder, created_at"
        )
        .in_("topic_id", topic_ids)
        .order("created_at")
        .execute()
    )
    return res.data


def _count(table: str, **eqs) -> int:
    q = get_service_client().table(table).select("id", count="exact", head=True)
    for col, val in eqs.items():
        q = q.eq(col, val)
    return q.execute().count or 0


def get_pipeline_summary(session_id: str) -> dict:
    """Status + expansion/plan counts for polling and the result views. Computed
    with count queries (cheap, indexed) so it scales past the 1000-row read cap.
    `plan` is null until the article-planning orchestrator has run."""
    session = get_session(session_id) or {}
    topics = list_topics(session_id)
    clog_topics = (session.get("statistical_clustering_log") or {}).get("topics") or {}
    olog = session.get("orchestrator_log") or {}

    clusters = list_clusters(session_id)
    gaps = list_coverage_gaps(session_id)
    clusters_by_topic: dict[str, int] = {}
    gaps_by_topic: dict[str, int] = {}
    for c in clusters:
        clusters_by_topic[c["topic_id"]] = clusters_by_topic.get(c["topic_id"], 0) + 1
    for g in gaps:
        gaps_by_topic[g["topic_id"]] = gaps_by_topic.get(g["topic_id"], 0) + 1

    expansion_topics = []
    for t in topics:
        tid = t["id"]
        expansion_topics.append({
            "topic_id": tid,
            "name": t["name"],
            "active": _count("keywords", topic_id=tid, status="active"),
            "total": _count("keywords", topic_id=tid),
            "grouping_count": (clog_topics.get(tid) or {}).get("grouping_count", 0),
        })

    has_plan = bool(clusters) or bool(olog)
    plan = None
    if has_plan:
        plan = {
            "clusters": len(clusters),
            "gaps": len(gaps),
            "dropped": _count("keywords", session_id=session_id,
                              status="dropped_by_orchestrator"),
            "collisions": len((olog.get("dedup") or {}).get("collisions") or []),
            "topics": [
                {
                    "topic_id": t["id"],
                    "name": t["name"],
                    "articles": clusters_by_topic.get(t["id"], 0),
                    "gaps": gaps_by_topic.get(t["id"], 0),
                }
                for t in topics
            ],
        }

    return {
        "status": session.get("status"),
        "last_error": session.get("last_error"),
        "expansion": {
            "counts": {
                "active": _count("keywords", session_id=session_id, status="active"),
                "filtered_relevance": _count("keywords", session_id=session_id,
                                             status="filtered_relevance"),
                "filtered_junk": _count("keywords", session_id=session_id,
                                        status="filtered_junk"),
            },
            "topics": expansion_topics,
        },
        "plan": plan,
    }


def list_coverage_gaps(session_id: str) -> list[dict]:
    topic_ids = [t["id"] for t in list_topics(session_id)]
    if not topic_ids:
        return []
    res = (
        get_service_client()
        .table("coverage_gaps")
        .select("id, topic_id, suggested_title, target_keyword, rationale, status, "
                "accepted_cluster_id, created_at")
        .in_("topic_id", topic_ids)
        .order("created_at")
        .execute()
    )
    return res.data
