"""Experiment 2 (preliminary) regression guard.

results/prototype/exp2_prelim_2026-11-22.csv is the run behind the HW9 section 6 table. If a change is
meant to alter these numbers, say so in the PR and add a new dated file; never edit this one.
"""
import csv
import statistics
from pathlib import Path

import pytest

from exp2 import SCENARIOS, SEEDS  # prototype/ is on sys.path via conftest
from system import run_baseline

CSV = Path(__file__).resolve().parents[1] / "results" / "prototype" / "exp2_prelim_2026-11-22.csv"


def rows() -> list[dict]:
    with CSV.open() as f:
        return list(csv.DictReader(f))


def csv_row(scenario: str, mode: str) -> dict:
    return next(r for r in rows() if r["scenario"] == scenario and r["reuse_mode"] == mode)


@pytest.mark.parametrize(
    "scenario,mode",
    [("highly_repeated", "cache_merge"), ("cold_burst", "none"), ("cold_burst", "cache"), ("cold_burst", "cache_merge")],
)
def test_exp2_matches_the_frozen_csv(scenario, mode):
    runs = [run_baseline(seed=s, reuse_mode=mode, **SCENARIOS[scenario]) for s in SEEDS]
    row = csv_row(scenario, mode)
    tput = [r["briefs_per_min"] for r in runs]
    assert round(statistics.median(tput), 3) == float(row["briefs_per_min_median"])
    assert round(min(tput), 3) == float(row["briefs_per_min_min"])
    assert round(max(tput), 3) == float(row["briefs_per_min_max"])
    assert statistics.median(r["upstream_calls"] for r in runs) == float(row["upstream_calls_median"])
    assert statistics.median(r["cache_hits"] for r in runs) == float(row["cache_hits_median"])
    assert statistics.median(r["merged"] for r in runs) == float(row["merged_median"])


def test_every_recorded_setting_has_no_wrong_briefs_and_no_violations():
    assert len(rows()) == len(SCENARIOS) * 3
    assert all(int(r["wrong_briefs_total"]) == 0 and int(r["violations_total"]) == 0 for r in rows())


def test_merging_finishes_more_of_a_cold_burst_than_the_cache_alone_with_non_overlapping_seed_ranges():
    cache, merge = csv_row("cold_burst", "cache"), csv_row("cold_burst", "cache_merge")
    assert float(merge["briefs_per_min_min"]) > float(cache["briefs_per_min_max"])
    assert float(merge["upstream_calls_median"]) < float(cache["upstream_calls_median"])
