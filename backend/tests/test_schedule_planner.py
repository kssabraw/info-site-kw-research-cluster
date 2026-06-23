"""M15 slice 3 — schedule planner (pure)."""

from datetime import date, datetime, time, timezone

import pytest

from app.writer.schedule_planner import (
    ScheduleError,
    finish_date,
    order_clusters,
    plan_runs,
    schedule_days,
)


# ----- ordering -------------------------------------------------------------

def _arch():
    return {"pillars": [
        {"topic_id": "t1", "supporting_article_ids": ["c2", "c1"]},
        {"topic_id": "t2", "supporting_article_ids": ["c3"]},
    ]}


def test_order_pillars_first_then_unreferenced():
    # c4 isn't in the architecture -> appended last (stable). architecture order wins for the rest.
    out = order_clusters(_arch(), ["c1", "c2", "c3", "c4"])
    assert out == ["c2", "c1", "c3", "c4"]


def test_order_no_architecture_keeps_input_order():
    assert order_clusters(None, ["c1", "c2"]) == ["c1", "c2"]


def test_order_drops_missing_and_dedups():
    # architecture references c9 (no longer a cluster) -> skipped; input dups collapsed.
    arch = {"pillars": [{"supporting_article_ids": ["c9", "c1"]}]}
    assert order_clusters(arch, ["c1", "c1", "c2"]) == ["c1", "c2"]


# ----- drip math ------------------------------------------------------------

def test_schedule_days_and_finish():
    assert schedule_days(315, 5) == 63
    assert schedule_days(10, 5) == 2
    assert schedule_days(11, 5) == 3
    assert finish_date(date(2026, 6, 16), 315, 5) == date(2026, 8, 17)   # 63 days inclusive


def test_all_at_once_all_due_now():
    now = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    runs = plan_runs(["a", "b", "c"], mode="all_at_once", now_utc=now)
    assert [r.scheduled_at for r in runs] == [now, now, now]
    assert [r.cluster_id for r in runs] == ["a", "b", "c"]


def test_drip_buckets_by_per_day_at_time_of_day_utc():
    runs = plan_runs(
        ["a", "b", "c"], mode="drip", per_day=2, start_date=date(2026, 6, 16),
        time_of_day=time(9, 0), tz_name="UTC",
    )
    # a,b on day 0 @ 09:00Z; c on day 1 @ 09:00Z
    assert runs[0].scheduled_at == datetime(2026, 6, 16, 9, 0, tzinfo=timezone.utc)
    assert runs[1].scheduled_at == datetime(2026, 6, 16, 9, 0, tzinfo=timezone.utc)
    assert runs[2].scheduled_at == datetime(2026, 6, 17, 9, 0, tzinfo=timezone.utc)


def test_drip_timezone_converts_to_utc():
    # 09:00 America/New_York (EDT, -4) on this date -> 13:00Z
    runs = plan_runs(
        ["a"], mode="drip", per_day=1, start_date=date(2026, 6, 16),
        time_of_day=time(9, 0), tz_name="America/New_York",
    )
    assert runs[0].scheduled_at == datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc)


def test_fixed_date_all_runs_on_chosen_day():
    # "deliver July 4 -> write July 3": every selected article scheduled for the same day.
    runs = plan_runs(
        ["a", "b", "c"], mode="fixed", start_date=date(2026, 7, 3),
        time_of_day=time(8, 0), tz_name="UTC",
    )
    assert all(r.scheduled_at == datetime(2026, 7, 3, 8, 0, tzinfo=timezone.utc) for r in runs)
    assert [r.cluster_id for r in runs] == ["a", "b", "c"]


def test_fixed_requires_a_date():
    with pytest.raises(ScheduleError):
        plan_runs(["a"], mode="fixed")


def test_drip_over_365_days_raises_with_hint():
    with pytest.raises(ScheduleError) as ei:
        plan_runs(["x"] * 400, mode="drip", per_day=1, start_date=date(2026, 6, 16),
                  time_of_day=time(9, 0))
    assert ei.value.min_per_day == 2          # ceil(400/365)


def test_empty_and_bad_mode_raise():
    with pytest.raises(ScheduleError):
        plan_runs([], mode="all_at_once")
    with pytest.raises(ScheduleError):
        plan_runs(["a"], mode="weekly")
    with pytest.raises(ScheduleError):
        plan_runs(["a"], mode="drip", per_day=0)
