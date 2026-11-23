"""Experiment 1 regression guard.

results/prototype/exp1_baseline_2026-11-22.csv is a frozen run of prototype/exp1.py (no reuse, one
subagent per question). With one subagent per job, the simulator must keep giving these numbers.
If a change is meant to alter them, say so in the PR and add a new dated baseline; never edit this one.
"""
import csv
import statistics
from pathlib import Path

import pytest

from system import run_baseline  # prototype/ is on sys.path via conftest

BASELINE = Path(__file__).resolve().parents[1] / "results" / "prototype" / "exp1_baseline_2026-11-22.csv"
SEEDS = (0, 1, 2)


def baseline_row(workers: int, rate: int) -> dict:
    with BASELINE.open() as f:
        for row in csv.DictReader(f):
            if int(row["workers"]) == workers and int(row["rate_per_min"]) == rate:
                return row
    raise KeyError((workers, rate))


@pytest.mark.parametrize("workers,rate", [(1, 1), (4, 4), (4, 12)])
def test_exp1_matches_frozen_baseline(workers, rate):
    runs = [run_baseline(workers, rate, seed=s) for s in SEEDS]
    tput = [r["briefs_per_min"] for r in runs]
    row = baseline_row(workers, rate)
    assert round(statistics.median(tput), 3) == float(row["briefs_per_min_median"])
    assert round(min(tput), 3) == float(row["briefs_per_min_min"])
    assert round(max(tput), 3) == float(row["briefs_per_min_max"])
    assert statistics.median(r["wasted_calls"] for r in runs) == float(row["wasted_calls_median"])
    assert statistics.median(r["expired"] for r in runs) == float(row["expired_median"])
    assert sum(r["violations"] for r in runs) == 0 == int(row["violations_total"])
