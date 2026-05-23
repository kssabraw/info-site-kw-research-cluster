"""Storage operations for sessions and topics (M2 silo discovery).

Reads that serve a user and ownership checks go through the user-scoped client
so RLS enforces visibility. Writes the backend orchestrates go through the
service client after ownership has been verified.
"""

from app.pipeline.models import ProposedSilo
from app.storage.supabase_client import (
    ensure_scratch_project,
    get_service_client,
    get_user_client,
)

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
_KEYWORD_COLS = "id, topic_id, keyword, sources, status, created_at"


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
    session_id: str, topic_id: str | None = None, limit: int = 200, offset: int = 0
) -> list[dict]:
    q = (
        get_service_client()
        .table("keywords")
        .select(_KEYWORD_COLS)
        .eq("session_id", session_id)
    )
    if topic_id:
        q = q.eq("topic_id", topic_id)
    res = q.order("created_at").range(offset, offset + limit - 1).execute()
    return res.data


def set_topic_embedding(topic_id: str, vector: list[float]) -> None:
    # pgvector accepts its text form "[a,b,c]".
    literal = "[" + ",".join(repr(float(x)) for x in vector) + "]"
    get_service_client().table("topics").update({"embedding": literal}).eq(
        "id", topic_id
    ).execute()
