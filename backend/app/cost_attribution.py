"""Bind a cost meter to a run and flush it to the session (PRD §16.4).

`metered_run` is for the background pipeline jobs: it binds a `CostMeter` on the
job thread (so nested worker threads inherit it via `ContextThreadPoolExecutor`),
spawns a daemon that flushes the running total to `sessions.actual_cost_usd` +
`cost_breakdown` every `cost_flush_interval_s`, and does a final flush on exit —
including on failure, so a crashed/partial run still records the cost spent so far
(§16.4 "final flush on step completion or session terminal state").

`metered_sync` is for the short synchronous silo-discovery call in the request
path: bind + single final flush, no periodic thread.

Cost accumulates across a session's runs (expand → plan → architecture, plus any
re-plan/regate/fanout): each run reads the existing total as its base and adds its
own metered spend, so the persisted figure is the session's real cumulative cost
(matches §16.4 "the session's running cost"). The per-session run guard
(`try_mark_running`) means two jobs never write the same row concurrently.
"""

import logging
import threading
from contextlib import contextmanager

from app.config import get_settings
from app.cost_meter import CostMeter, bind_meter, set_step
from app.storage import silo as store

logger = logging.getLogger(__name__)


def _merge(base: dict[str, float], delta: dict[str, float]) -> dict[str, float]:
    merged = dict(base)
    for step, cost in delta.items():
        merged[step] = round(merged.get(step, 0.0) + cost, 6)
    return merged


def _flush(session_id: str, meter: CostMeter, base_total: float, base_breakdown: dict) -> None:
    total, breakdown = meter.snapshot()
    try:
        store.flush_session_cost(
            session_id,
            round(base_total + total, 6),
            _merge(base_breakdown, breakdown),
        )
    except Exception as exc:  # noqa: BLE001 — a flush failure must not kill the run
        logger.warning(
            "cost_flush_failed",
            extra={"event": "cost_flush_failed", "reason": repr(exc)},
        )


@contextmanager
def metered_run(session_id: str, step: str):
    """Background-job metering: periodic + final flush (PRD §16.4)."""
    base_total, base_breakdown = store.get_session_cost(session_id)
    meter = CostMeter()
    bind_meter(meter)
    set_step(step)
    interval = float(get_settings().cost_flush_interval_s)
    stop = threading.Event()
    # Serialize DB writes so the final flush is always the last write: once stop is
    # set the loop never starts another flush, so at most one periodic flush can be
    # in flight, and the final flush blocks on this lock until it finishes — then
    # writes the largest (latest) value. Without it, a slow periodic flush could
    # land after the final one and overwrite it with a slightly stale total.
    flush_lock = threading.Lock()

    def do_flush() -> None:
        with flush_lock:
            _flush(session_id, meter, base_total, base_breakdown)

    def loop() -> None:
        while not stop.wait(interval):
            do_flush()

    flusher = threading.Thread(target=loop, name=f"cost-flush-{step}", daemon=True)
    flusher.start()
    try:
        yield meter
    finally:
        stop.set()
        flusher.join(timeout=2.0)
        do_flush()
        bind_meter(None)


@contextmanager
def metered_sync(session_id: str, step: str):
    """Synchronous metering for the in-request silo-discovery call: a single
    final flush, no periodic thread (the call is quick)."""
    base_total, base_breakdown = store.get_session_cost(session_id)
    meter = CostMeter()
    bind_meter(meter)
    set_step(step)
    try:
        yield meter
    finally:
        _flush(session_id, meter, base_total, base_breakdown)
        bind_meter(None)
