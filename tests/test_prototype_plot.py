"""Tests for prototype/plot_exp1.py (the HW9 section 6 figure).

The data loader is pure (csv only), so it is always tested. Rendering needs matplotlib, which is
not a project dependency yet (task M1 adds the dev extra), so that test skips without it.
"""
from pathlib import Path

import pytest

import plot_exp1  # prototype/ is on sys.path via conftest

BASELINE = Path(__file__).resolve().parents[1] / "results" / "prototype" / "exp1_baseline_2026-11-22.csv"


def test_provider_ceiling_is_twenty_calls_a_minute_over_k():
    assert plot_exp1.PROVIDER_CALLS_PER_MIN == pytest.approx(20.0)
    assert plot_exp1.ceiling_briefs_per_min(k=5) == pytest.approx(4.0)
    assert plot_exp1.ceiling_briefs_per_min(k=10) == pytest.approx(2.0)


def test_load_series_groups_the_baseline_by_worker_count_in_rate_order():
    series = plot_exp1.load_series(BASELINE)
    assert sorted(series) == [1, 2, 4]
    for points in series.values():
        rates = [p.rate for p in points]
        assert rates == sorted(rates) == [1, 2, 3, 4, 5, 6, 8, 12]


def test_load_series_carries_the_median_and_the_seed_range():
    four = {p.rate: p for p in plot_exp1.load_series(BASELINE)[4]}
    assert four[4].median == pytest.approx(3.267)
    assert four[4].low == pytest.approx(3.133)
    assert four[4].high == pytest.approx(3.5)
    assert four[12].median == pytest.approx(0.267)


def test_no_median_exceeds_the_provider_ceiling():
    ceiling = plot_exp1.ceiling_briefs_per_min(k=5)
    for points in plot_exp1.load_series(BASELINE).values():
        assert all(p.low <= p.median <= p.high for p in points)
        assert all(p.median <= ceiling for p in points)


def test_peak_finds_the_best_point_per_worker_count():
    series = plot_exp1.load_series(BASELINE)
    assert plot_exp1.peak(series[4]).rate == 4
    assert plot_exp1.peak(series[2]).rate == 3
    assert plot_exp1.peak(series[1]).rate == 1


def test_load_series_names_a_missing_column(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("workers,rate_per_min\n1,1\n")
    with pytest.raises(ValueError, match="briefs_per_min_median"):
        plot_exp1.load_series(bad)


def test_render_writes_a_png(tmp_path):
    pytest.importorskip("matplotlib")
    out = tmp_path / "fig.png"
    plot_exp1.render(plot_exp1.load_series(BASELINE), out)
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert out.stat().st_size > 10_000
