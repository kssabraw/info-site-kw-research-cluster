"""Writer article persistence (`fanout.article_outputs`). Latest-by-generated_at wins
(history kept). Reads run as the service role here; the API GET is RLS-scoped to a
visible session."""

from __future__ import annotations

from app.storage.supabase_client import get_service_client


def get_latest_article(cluster_id: str) -> dict | None:
    res = (
        get_service_client()
        .table("article_outputs")
        .select("*")
        .eq("cluster_id", cluster_id)
        .order("generated_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def save_article(
    *, cluster_id: str, session_id: str, article_json: dict, article_markdown: str,
    article_html: str, total_word_count: int | None, cost_usd: float | None,
    schema_version_effective: str,
) -> dict:
    res = (
        get_service_client()
        .table("article_outputs")
        .insert({
            "cluster_id": cluster_id, "session_id": session_id,
            "article_json": article_json, "article_markdown": article_markdown,
            "article_html": article_html, "total_word_count": total_word_count,
            "cost_usd": cost_usd, "schema_version_effective": schema_version_effective,
        })
        .execute()
    )
    return res.data[0]
