"""M11 — cost attribution (PRD §16.4).

Pure unit coverage of the metering primitives: the pricing table, the thread-safe
`CostMeter`, context propagation into nested worker threads (the whole reason for
`ContextThreadPoolExecutor`), and the accumulate-onto-base flush logic in
`cost_attribution`. No DB / no egress.
"""

import app.cost_attribution as ca
from app.concurrency import ContextThreadPoolExecutor
from app.cost_meter import (
    CostMeter,
    bind_meter,
    current_meter,
    embedding_token_cost,
    llm_token_cost,
    record_cost,
    set_step,
)


def test_llm_token_cost_known_and_default():
    # Opus rate (5/25 per 1M, published list price): 1000 in + 500 out.
    c = llm_token_cost("claude-opus-4-7", 1000, 500)
    assert c == round(1000 / 1e6 * 5 + 500 / 1e6 * 25, 6)
    # Unknown model falls back to the default rate, not a crash.
    assert llm_token_cost("some-unknown-model", 1000, 0) is not None


def test_llm_token_cost_prefix_match():
    # A versioned model id should match the known prefix.
    assert llm_token_cost("claude-opus-4-7-20260101", 1_000_000, 0) == 5.0


def test_llm_token_cost_none_when_no_tokens():
    assert llm_token_cost("claude-opus-4-7", None, None) is None


def test_embedding_token_cost():
    assert embedding_token_cost("text-embedding-3-small", 1_000_000) == 0.02
    assert embedding_token_cost("text-embedding-3-small", None) is None


def test_meter_accumulates_by_step():
    m = CostMeter()
    m.add(0.10, "expand")
    m.add(0.05, "expand")
    m.add(0.30, "architecture")
    m.add(None, "expand")  # None is a no-op
    total, breakdown = m.snapshot()
    assert total == 0.45
    assert breakdown == {"expand": 0.15, "architecture": 0.30}


def test_record_cost_noop_without_bound_meter():
    bind_meter(None)
    record_cost(1.23)  # must not raise
    assert current_meter() is None


def test_record_cost_reaches_meter_through_nested_threads():
    """The crux: a meter bound on this thread must be visible to `record_cost`
    called inside a ContextThreadPoolExecutor worker (PRD §16.3/§16.4)."""
    meter = CostMeter()
    bind_meter(meter)
    set_step("expand")

    def work(cost: float):
        record_cost(cost)  # runs in a worker thread

    with ContextThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(work, [0.01, 0.02, 0.03, 0.04]))

    total, breakdown = meter.snapshot()
    bind_meter(None)
    assert round(total, 6) == 0.10
    assert breakdown == {"expand": 0.10}


def test_plain_executor_does_not_propagate(monkeypatch):
    """Sanity check that the propagation is doing real work: a raw executor would
    NOT see the bound meter (so the cost would be lost). Confirms the fix matters."""
    from concurrent.futures import ThreadPoolExecutor

    meter = CostMeter()
    bind_meter(meter)
    set_step("expand")
    with ThreadPoolExecutor(max_workers=2) as ex:
        list(ex.map(lambda c: record_cost(c), [0.5, 0.5]))
    total, _ = meter.snapshot()
    bind_meter(None)
    assert total == 0.0  # lost, because contextvars don't cross into raw workers


def test_make_flusher_sends_only_incremental_deltas(monkeypatch):
    """Repeated flushes of the same meter send only the spend since the previous flush —
    so concurrent same-session writers accumulate correctly (no double-count, no lost base)."""
    calls: list[tuple] = []
    monkeypatch.setattr(
        ca.store, "increment_session_cost",
        lambda sid, dt, db: calls.append((round(dt, 6), dict(db))),
    )
    meter = CostMeter()
    bind_meter(meter)
    set_step("article_generation")
    flush = ca._make_flusher("s1", meter)

    record_cost(0.30)
    flush()                                   # first flush: +0.30
    record_cost(0.20)
    flush()                                   # second flush: only the new +0.20
    flush()                                   # no change -> no-op (no extra call)
    bind_meter(None)

    assert calls == [
        (0.30, {"article_generation": 0.30}),
        (0.20, {"article_generation": 0.20}),
    ]


def test_metered_sync_increments_by_metered_delta(monkeypatch):
    """metered_sync atomically increments the session cost by its metered spend (the DB-side
    increment accumulates onto whatever's already there — no Python base read)."""
    inc = {"total": 0.0, "breakdown": {}}

    def fake_increment(sid, delta_total, delta_breakdown):
        inc["total"] = round(inc["total"] + delta_total, 6)
        for k, v in delta_breakdown.items():
            inc["breakdown"][k] = round(inc["breakdown"].get(k, 0.0) + v, 6)

    monkeypatch.setattr(ca.store, "increment_session_cost", fake_increment)

    with ca.metered_sync("s1", "article_planning"):
        record_cost(0.60)
        record_cost(0.10)

    assert inc["total"] == 0.70
    assert inc["breakdown"] == {"article_planning": 0.70}
    # The meter is unbound on exit so a later record_cost is a no-op.
    assert current_meter() is None
