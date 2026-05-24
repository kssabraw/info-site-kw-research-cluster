"""Owner-only diagnostics. Temporary: used to inspect raw DataForSEO responses
while tuning expansion anchors/parsing. Safe to remove once tuning is done."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import AuthedUser, require_user
from app.dataforseo import get_dataforseo
from app.storage.supabase_client import get_service_client

logger = logging.getLogger(__name__)
router = APIRouter(tags=["debug"])

_LOC = 2840
_LANG = "en"


def _require_owner(user: AuthedUser) -> None:
    prof = (
        get_service_client()
        .table("user_profiles")
        .select("role")
        .eq("user_id", user.id)
        .limit(1)
        .execute()
    )
    if not prof.data or prof.data[0].get("role") != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner only")


@router.get("/debug/dataforseo")
def debug_dataforseo(keyword: str, user: AuthedUser = Depends(require_user)) -> dict:
    """Fire one call to each Labs/SERP endpoint for `keyword` and report the raw
    shape (task status, item count, first items) so anchor/parse issues are
    visible without guessing."""
    _require_owner(user)
    dfs = get_dataforseo()
    probes = {
        "keyword_suggestions": (
            "/v3/dataforseo_labs/google/keyword_suggestions/live",
            [{"keyword": keyword, "location_code": _LOC, "language_code": _LANG, "limit": 50}],
        ),
        "related_keywords": (
            "/v3/dataforseo_labs/google/related_keywords/live",
            [{"keyword": keyword, "location_code": _LOC, "language_code": _LANG,
              "depth": 2, "limit": 50}],
        ),
        "autocomplete": (
            "/v3/serp/google/autocomplete/live/advanced",
            [{"keyword": keyword, "location_code": _LOC, "language_code": _LANG}],
        ),
    }
    out: dict = {"keyword": keyword}
    for name, (path, payload) in probes.items():
        try:
            body = dfs.raw(path, payload)
        except Exception as exc:  # noqa: BLE001 — surface anything for diagnosis
            out[name] = {"error": repr(exc)}
            continue
        task = (body.get("tasks") or [{}])[0] if isinstance(body, dict) else {}
        result = task.get("result") or []
        items = (result[0].get("items") if result and isinstance(result[0], dict) else None) or []
        out[name] = {
            "task_status_code": task.get("status_code"),
            "task_status_message": task.get("status_message"),
            "result_count": len(items),
            "first_items": items[:2],
        }
    return out
