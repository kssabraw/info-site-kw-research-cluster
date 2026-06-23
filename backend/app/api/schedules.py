"""M15 slice 5 — content scheduling API (handoff.md §9.4 / §9.9).

`Schedule all` (or a chosen subset) materializes a `content_schedules` parent + one
`scheduled_article_runs` per cluster; the slice-4 worker drains them at their `scheduled_at`.
Three modes: all-at-once, drip N/day, or a specific date (deliver-by). Both roles act on
sessions they can see (RLS via `_require_session`); a VA whose batch estimate exceeds
`writer_schedule_approval_threshold_usd` ($90) is blocked pending owner approval (the owner
is never gated). Pause = toggle the parent (the worker's claim only takes `active` schedules).
"""

from __future__ import annotations

import logging
from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.sessions import _require_session
from app.auth import AuthedUser, require_user
from app.auth.dependencies import get_role
from app.config import get_settings
from app.storage import silo as store
from app.writer import schedule_store
from app.writer.schedule_planner import ScheduleError, finish_date, order_clusters, plan_runs

logger = logging.getLogger(__name__)
router = APIRouter()


class ScheduleBody(BaseModel):
    mode: str                                   # all_at_once | drip | fixed
    cluster_ids: list[str] | None = None        # None/[] -> the whole session
    per_day: int | None = None                  # drip
    start_date: date | None = None              # drip start / fixed target day
    time_of_day: time | None = None
    timezone: str = "UTC"
    site_base_url: str | None = None            # persisted to the session (links need it)


# ----- helpers --------------------------------------------------------------


def _resolve_targets(session_id: str, cluster_ids: list[str] | None) -> tuple[list[str], dict]:
    """Ordered (pillars-first) target cluster ids for this schedule + the architecture dict.
    A subset is intersected with the session's clusters (and ordered the same way)."""
    architecture = (store.get_architecture(session_id) or {}).get("architecture_json")
    all_ids = [c["id"] for c in store.list_clusters(session_id)]
    ordered = order_clusters(architecture, all_ids)
    if cluster_ids:
        chosen = set(cluster_ids)
        ordered = [cid for cid in ordered if cid in chosen]
    return ordered, architecture


def _estimate(count: int, mode: str, per_day: int | None, start: date | None) -> dict:
    s = get_settings()
    cost = round(count * s.writer_article_cost_estimate_usd, 2)
    out = {"count": count, "cost_estimate_usd": cost, "mode": mode}
    if mode == "drip" and per_day and count:
        from app.writer.schedule_planner import schedule_days
        days = schedule_days(count, per_day)
        out["days"] = days
        if start:
            out["finish_date"] = finish_date(start, count, per_day).isoformat()
    elif mode == "fixed" and start:
        out["finish_date"] = start.isoformat()
    return out


# ----- endpoints ------------------------------------------------------------


@router.post("/sessions/{session_id}/schedule-estimate")
def schedule_estimate(
    session_id: str, body: ScheduleBody, user: AuthedUser = Depends(require_user)
) -> dict:
    """Preview a schedule without creating it: count (after the double-book filter), cost,
    drip finish date, and whether a VA would need owner approval."""
    _require_session(user, session_id)
    ordered, _ = _resolve_targets(session_id, body.cluster_ids)
    pending = schedule_store.pending_cluster_ids(session_id)
    targets = [c for c in ordered if c not in pending]
    est = _estimate(len(targets), body.mode, body.per_day, body.start_date)
    est["already_scheduled"] = len(ordered) - len(targets)
    s = get_settings()
    est["requires_approval"] = (
        get_role(user) != "owner" and est["cost_estimate_usd"] > s.writer_schedule_approval_threshold_usd
    )
    est["approval_threshold_usd"] = s.writer_schedule_approval_threshold_usd
    return est


@router.post("/sessions/{session_id}/schedule")
def create_schedule(
    session_id: str, body: ScheduleBody, user: AuthedUser = Depends(require_user)
) -> dict:
    """Validate + plan + materialize a schedule. Persists `site_base_url` to the session if
    supplied. Skips clusters already queued in another active schedule (double-book guard).
    A VA over the $90 batch threshold is refused with `requires_approval` (owner not gated)."""
    session = _require_session(user, session_id)

    base_url = (body.site_base_url or "").strip() or session.get("site_base_url")
    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A site base URL is required so internal links are absolute. Set it in the modal.",
        )
    if body.site_base_url and body.site_base_url.strip() != session.get("site_base_url"):
        store.update_session(session_id, {"site_base_url": body.site_base_url.strip()})

    ordered, architecture = _resolve_targets(session_id, body.cluster_ids)
    pending = schedule_store.pending_cluster_ids(session_id)
    targets = [c for c in ordered if c not in pending]
    skipped = len(ordered) - len(targets)
    if not targets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nothing to schedule (no clusters, or all are already scheduled).",
        )

    est = _estimate(len(targets), body.mode, body.per_day, body.start_date)
    s = get_settings()
    if get_role(user) != "owner" and est["cost_estimate_usd"] > s.writer_schedule_approval_threshold_usd:
        return {
            "status": "requires_approval", "created": False,
            "estimate": est, "skipped": skipped,
            "approval_threshold_usd": s.writer_schedule_approval_threshold_usd,
        }

    try:
        runs = plan_runs(
            targets, mode=body.mode, per_day=body.per_day, start_date=body.start_date,
            time_of_day=body.time_of_day, tz_name=body.timezone,
        )
    except ScheduleError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": str(exc), "min_per_day": exc.min_per_day},
        ) from exc

    schedule = schedule_store.create_schedule(
        session_id=session_id, user_id=session["user_id"], mode=body.mode, runs=runs,
        per_day=body.per_day, start_date=body.start_date, time_of_day=body.time_of_day,
        tz_name=body.timezone,
    )
    logger.info("schedule_created", extra={"event": "schedule_created", "session_id": session_id,
                                           "mode": body.mode, "runs": len(runs), "skipped": skipped})
    return {"status": "scheduled", "created": True, "schedule": schedule,
            "scheduled": len(runs), "skipped": skipped, "estimate": est}


@router.get("/sessions/{session_id}/schedules")
def list_schedules(session_id: str, user: AuthedUser = Depends(require_user)) -> dict:
    """The session's schedule batches with live progress counts (for the overview UI)."""
    _require_session(user, session_id)
    schedules = schedule_store.list_schedules(session_id)
    for sch in schedules:
        sch["progress"] = schedule_store.schedule_progress(sch["id"])
    return {"schedules": schedules}


@router.get("/sessions/{session_id}/schedule-runs")
def list_schedule_runs(session_id: str, user: AuthedUser = Depends(require_user)) -> dict:
    """All scheduled runs for a session (cluster, scheduled_at, status, error)."""
    _require_session(user, session_id)
    return {"runs": schedule_store.list_runs(session_id)}


def _require_schedule(user: AuthedUser, session_id: str, schedule_id: str) -> dict:
    _require_session(user, session_id)
    sched = schedule_store.get_schedule(schedule_id)
    if not sched or sched["session_id"] != session_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return sched


@router.post("/sessions/{session_id}/schedules/{schedule_id}/pause")
def pause_schedule(session_id: str, schedule_id: str, user: AuthedUser = Depends(require_user)) -> dict:
    _require_schedule(user, session_id, schedule_id)
    schedule_store.set_schedule_status(schedule_id, "paused")
    return {"status": "paused"}


@router.post("/sessions/{session_id}/schedules/{schedule_id}/resume")
def resume_schedule(session_id: str, schedule_id: str, user: AuthedUser = Depends(require_user)) -> dict:
    _require_schedule(user, session_id, schedule_id)
    schedule_store.set_schedule_status(schedule_id, "active")
    return {"status": "active"}


@router.post("/sessions/{session_id}/schedules/{schedule_id}/cancel")
def cancel_schedule(session_id: str, schedule_id: str, user: AuthedUser = Depends(require_user)) -> dict:
    _require_schedule(user, session_id, schedule_id)
    cancelled = schedule_store.cancel_schedule(schedule_id)
    return {"status": "cancelled", "cancelled_runs": cancelled}
