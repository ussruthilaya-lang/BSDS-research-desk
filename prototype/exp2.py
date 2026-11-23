"""Experiment 2 (preliminary, single-subagent jobs): what do the cache and merging buy?

Three reuse modes (none, cache, cache_merge) on three workloads, 3 seeds each:

  mostly_unique   4 workers, 6 arrivals/min, pool of 5000 queries, no skew (~4% repeated searches)
  highly_repeated 4 workers, 6 arrivals/min, pool of 30 queries, skew 1.2 (~90% repeated searches)
  cold_burst      12 workers, 24 jobs arriving within about 12 s on an empty cache, same pool as above

6 arrivals a minute is past the no-reuse ceiling (20 calls/min / 5 searches = 4 briefs/min), so the
runs show whether reuse lifts the ceiling. Fan-out, corpus versions (staleness) and the Experiment 3
gather policies are not modelled yet. Writes results/prototype/exp2_prelim_2026-11-22.csv.

    python prototype/exp2.py
"""
import csv
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from system import run_baseline  # noqa: E402

MODES = ("none", "cache", "cache_merge")
SEEDS = (0, 1, 2)
REPEATED = dict(pool_size=30, skew=1.2)
SCENARIOS = {
    "mostly_unique": dict(workers=4, rate_per_min=6, duration_s=1800, pool_size=5000, skew=0.0),
    "highly_repeated": dict(workers=4, rate_per_min=6, duration_s=1800, **REPEATED),
    "cold_burst": dict(workers=12, rate_per_min=120, n_questions=24, duration_s=600, **REPEATED),
}
OUT = Path(__file__).resolve().parents[1] / "results" / "prototype" / "exp2_prelim_2026-11-22.csv"


def median_of(runs: list[dict], key: str) -> float:
    return statistics.median(r[key] for r in runs)


def rounded(value: float, digits: int):
    """Round for the CSV; blank when there is no value (no brief finished, so no ratio or p95)."""
    return "" if value != value else round(value, digits)


def main() -> None:
    rows = []
    for scenario, params in SCENARIOS.items():
        for mode in MODES:
            runs = [run_baseline(seed=s, reuse_mode=mode, **params) for s in SEEDS]
            tput = [r["briefs_per_min"] for r in runs]
            rows.append(
                {
                    "scenario": scenario,
                    "reuse_mode": mode,
                    "workers": params["workers"],
                    "rate_per_min": params["rate_per_min"],
                    "briefs_per_min_median": round(statistics.median(tput), 3),
                    "briefs_per_min_min": round(min(tput), 3),
                    "briefs_per_min_max": round(max(tput), 3),
                    "on_time_correct_median": median_of(runs, "on_time_correct"),
                    "upstream_calls_median": median_of(runs, "upstream_calls"),
                    "calls_per_brief_median": rounded(median_of(runs, "calls_per_brief"), 2),
                    "cache_hits_median": median_of(runs, "cache_hits"),
                    "merged_median": median_of(runs, "merged"),
                    "p95_latency_s_median": rounded(median_of(runs, "p95_latency_s"), 1),
                    "expired_median": median_of(runs, "expired"),
                    "wrong_briefs_total": sum(r["wrong_briefs"] for r in runs),
                    "violations_total": sum(r["violations"] for r in runs),
                }
            )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"{'scenario':<16}{'mode':<13}{'briefs/min (min-max)':>24}{'on-time':>8}{'calls':>7}{'calls/brief':>12}"
          f"{'hits':>6}{'merged':>7}{'p95 s':>7}{'expired':>8}")
    for r in rows:
        span = f"{r['briefs_per_min_median']:.2f} ({r['briefs_per_min_min']:.2f}-{r['briefs_per_min_max']:.2f})"
        print(f"{r['scenario']:<16}{r['reuse_mode']:<13}{span:>24}{r['on_time_correct_median']:>8.0f}"
              f"{r['upstream_calls_median']:>7.0f}{r['calls_per_brief_median']:>12}{r['cache_hits_median']:>6.0f}"
              f"{r['merged_median']:>7.0f}{r['p95_latency_s_median']:>7}{r['expired_median']:>8.0f}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
