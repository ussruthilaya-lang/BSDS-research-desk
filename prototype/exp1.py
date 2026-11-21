"""Experiment 1 (prototype): where do extra workers stop helping?

No reuse, unique searches, 1/2/4 workers, rising arrival rates, 3 seeds per setting.
Reports median and range of briefs completed on time per minute. Writes a CSV.

    python prototype/exp1.py
"""
import csv
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from system import run_baseline  # noqa: E402

WORKERS = (1, 2, 4)
RATES = (1, 2, 3, 4, 5, 6, 8, 12)  # arrivals per minute
SEEDS = (0, 1, 2)
OUT = Path(__file__).resolve().parents[1] / "results" / "prototype" / "exp1_scaling.csv"


def main() -> None:
    rows = []
    for workers in WORKERS:
        for rate in RATES:
            runs = [run_baseline(workers, rate, seed=s) for s in SEEDS]
            tput = [r["briefs_per_min"] for r in runs]
            rows.append(
                {
                    "workers": workers,
                    "rate_per_min": rate,
                    "briefs_per_min_median": round(statistics.median(tput), 3),
                    "briefs_per_min_min": round(min(tput), 3),
                    "briefs_per_min_max": round(max(tput), 3),
                    "p95_latency_s_median": round(statistics.median(r["p95_latency_s"] for r in runs), 1),
                    "max_gateway_depth_median": statistics.median(r["max_queue_depth"] for r in runs),
                    "max_pending_median": statistics.median(r["max_pending"] for r in runs),
                    "wasted_calls_median": statistics.median(r["wasted_calls"] for r in runs),
                    "expired_median": statistics.median(r["expired"] for r in runs),
                    "rejected_median": statistics.median(r["rejected"] for r in runs),
                    "violations_total": sum(r["violations"] for r in runs),
                }
            )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"{'workers':>7} {'rate':>5} {'briefs/min (min-max)':>24} {'p95 s':>7} "
        f"{'gw depth':>9} {'backlog':>8} {'expired':>8} {'wasted':>7}"
    )
    for r in rows:
        span = f"{r['briefs_per_min_median']:.2f} ({r['briefs_per_min_min']:.2f}-{r['briefs_per_min_max']:.2f})"
        print(
            f"{r['workers']:>7} {r['rate_per_min']:>5} {span:>24} {r['p95_latency_s_median']:>7} "
            f"{r['max_gateway_depth_median']:>9} {r['max_pending_median']:>8} "
            f"{r['expired_median']:>8} {r['wasted_calls_median']:>7}"
        )
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
