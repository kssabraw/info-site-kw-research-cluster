"""M9 — run cost model + approval-gate decision (PRD §8.1 / §8.4 / §11.3).

Pure-function tests: no DB, no egress. They pin the model to the §8.1 table's
intent — standard+metrics and comprehensive+metrics stay under the $5 VA cap,
recursive and oversized runs exceed it — rather than to exact cents (the table is
itself an estimate to be recalibrated after the first production runs)."""

from app.cost import estimate_cost, requires_approval

_CAP = 5.00


def test_reference_config_matches_table_within_tolerance():
    # §8.1 reference: 5 silos, 3 deep-mined.
    std = estimate_cost(coverage_mode="standard", silo_count=5, deep_mine_count=3)
    comp = estimate_cost(coverage_mode="comprehensive", silo_count=5, deep_mine_count=3)
    # Table subtotals (metrics off): 2.80 / 3.80. Allow a small modelling margin.
    assert abs(std.total_usd - 2.80) <= 0.30
    assert abs(comp.total_usd - 3.80) <= 0.40
    assert std.recursive_multiplier is None


def test_standard_and_comprehensive_with_metrics_under_cap():
    # §8.4: both modes with metrics on must pass the VA cap without approval.
    std = estimate_cost(
        coverage_mode="standard", silo_count=5, deep_mine_count=3,
        enrich_with_metrics=True,
    )
    comp = estimate_cost(
        coverage_mode="comprehensive", silo_count=5, deep_mine_count=2,
        enrich_with_metrics=True,
    )
    assert std.total_usd <= _CAP
    assert comp.total_usd <= _CAP


def test_metrics_increases_cost():
    off = estimate_cost(coverage_mode="standard", silo_count=5, deep_mine_count=1)
    on = estimate_cost(
        coverage_mode="standard", silo_count=5, deep_mine_count=1,
        enrich_with_metrics=True,
    )
    assert on.total_usd > off.total_usd
    assert "metrics_enrichment" in on.breakdown
    assert "metrics_enrichment" not in off.breakdown


def test_more_gated_silos_costs_more():
    a = estimate_cost(coverage_mode="comprehensive", silo_count=5, deep_mine_count=1)
    b = estimate_cost(coverage_mode="comprehensive", silo_count=5, deep_mine_count=4)
    assert b.total_usd > a.total_usd


def test_recursive_multiplies_and_exceeds_cap():
    base = estimate_cost(coverage_mode="standard", silo_count=5, deep_mine_count=3)
    rec = estimate_cost(
        coverage_mode="standard", silo_count=5, deep_mine_count=3, recursive_fanout=True
    )
    assert rec.recursive_multiplier == 5.0
    assert rec.total_usd > base.total_usd
    assert rec.total_usd > _CAP


def test_oversized_comprehensive_run_exceeds_cap():
    # A 10-silo comprehensive run with metrics is the "unusually expensive"
    # non-recursive case §8.4 expects to require approval.
    big = estimate_cost(
        coverage_mode="comprehensive", silo_count=10, deep_mine_count=2,
        enrich_with_metrics=True,
    )
    assert big.total_usd > _CAP


def test_unknown_mode_falls_back_to_standard():
    bad = estimate_cost(coverage_mode="bogus", silo_count=5, deep_mine_count=3)
    std = estimate_cost(coverage_mode="standard", silo_count=5, deep_mine_count=3)
    assert bad.total_usd == std.total_usd


def test_negative_deep_mine_clamped():
    est = estimate_cost(coverage_mode="standard", silo_count=5, deep_mine_count=-3)
    # Still counts the always-mined seed (1 unit), never negative mining cost.
    assert est.breakdown["competitor_mining"] > 0


def test_requires_approval_gate():
    # Under cap, no recursion -> runs directly.
    needs, triggers = requires_approval(
        estimated_cost_usd=3.0, soft_cap_usd=_CAP, recursive_fanout=False
    )
    assert needs is False and triggers == []
    # Over cap -> approval.
    needs, triggers = requires_approval(
        estimated_cost_usd=7.5, soft_cap_usd=_CAP, recursive_fanout=False
    )
    assert needs is True and "over_soft_cap" in triggers
    # Recursive always trips the gate, even when cheap.
    needs, triggers = requires_approval(
        estimated_cost_usd=1.0, soft_cap_usd=_CAP, recursive_fanout=True
    )
    assert needs is True and "recursive_fanout" in triggers
