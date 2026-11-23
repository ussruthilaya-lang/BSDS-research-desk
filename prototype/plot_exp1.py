"""Figure for HW9 section 6: briefs per minute against arrival rate, one line per worker count.

Reads the frozen Experiment 1 baseline (never writes it) and renders a PNG.

    pip install matplotlib        # only needed to render; loading the data needs just the stdlib
    python prototype/plot_exp1.py
    python prototype/plot_exp1.py --csv results/prototype/<other>.csv --out some.png
"""
import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "results" / "prototype" / "exp1_baseline_2026-11-22.csv"
DEFAULT_OUT = ROOT / "results" / "prototype" / "exp1_briefs_per_min.png"

PROVIDER_CALLS_PER_MIN = 20.0  # one call start every 3 s (prototype/sim.py Backend defaults)
BASELINE_K = 5  # the baseline runs one subagent per job with 5 searches

REQUIRED_COLUMNS = (
    "workers",
    "rate_per_min",
    "briefs_per_min_median",
    "briefs_per_min_min",
    "briefs_per_min_max",
)

# Reference palette, light mode, validated all-pairs with the dataviz skill's validate_palette.js.
# Colour follows the entity (worker count), never its rank.
SURFACE, INK, INK_2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
WORKER_COLOURS = {1: "#2a78d6", 2: "#eb6834", 4: "#1baf7a"}  # blue, orange, aqua


@dataclass(frozen=True)
class Point:
    rate: float  # arrivals per minute
    median: float  # briefs per minute, median of the seeds
    low: float  # worst seed
    high: float  # best seed


def ceiling_briefs_per_min(k: int) -> float:
    """Most briefs per minute the provider allows when every brief needs k calls and nothing is reused."""
    return PROVIDER_CALLS_PER_MIN / k


def load_series(path: Path) -> dict[int, list[Point]]:
    """Group the CSV rows by worker count; each list is in arrival-rate order."""
    with Path(path).open(newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing column(s) {', '.join(missing)}")
        grouped = defaultdict(list)
        for row in reader:
            grouped[int(row["workers"])].append(
                Point(
                    float(row["rate_per_min"]),
                    float(row["briefs_per_min_median"]),
                    float(row["briefs_per_min_min"]),
                    float(row["briefs_per_min_max"]),
                )
            )
    return {w: sorted(points, key=lambda p: p.rate) for w, points in sorted(grouped.items())}


def peak(points: list[Point]) -> Point:
    """The arrival rate with the highest median throughput."""
    return max(points, key=lambda p: p.median)


def render(series: dict[int, list[Point]], out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"]

    fig, ax = plt.subplots(figsize=(6.6, 4.0), dpi=200, facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ceiling = ceiling_briefs_per_min(BASELINE_K)

    ax.axhline(ceiling, color=INK_2, lw=1.0, zorder=1)
    ax.text(12.4, ceiling + 0.07, f"Provider ceiling: 20 calls/min ÷ {BASELINE_K} = {ceiling:g} briefs/min",
            ha="right", va="bottom", fontsize=7.5, color=INK_2)

    for workers, points in series.items():
        colour = WORKER_COLOURS[workers]
        x = [p.rate for p in points]
        ax.fill_between(x, [p.low for p in points], [p.high for p in points], color=colour, alpha=0.12, lw=0, zorder=2)
        ax.plot(x, [p.median for p in points], color=colour, lw=2, solid_capstyle="round", solid_joinstyle="round",
                marker="o", ms=7, mfc=colour, mec=SURFACE, mew=2, zorder=3,
                label=f"{workers} worker{'s' if workers > 1 else ''}")

    # Direct series labels sit where the lines are far apart (the lines converge at the right edge).
    # They wear text ink; identity comes from the adjacent line, plus the legend.
    for text, xy in (("4 workers", (1.15, 2.95)), ("2 workers", (3.12, 2.22)), ("1 worker", (3.1, 0.62))):
        ax.text(*xy, text, fontsize=7.5, color=INK_2, ha="left", va="bottom")

    # Selective labels: the peak of the best line, and the collapse. Not a number on every point.
    best = peak(series[4])
    ax.text(best.rate + 0.3, best.median + 0.02, f"Peak {best.median:.2f} at {best.rate:g} arrivals/min",
            fontsize=7.5, color=INK, va="bottom", ha="left")
    end = series[4][-1]
    ax.annotate(f"Collapses to {end.median:.2f} at {end.rate:g}/min", xy=(end.rate - 0.05, end.median + 0.06),
                xytext=(7.4, 1.55), fontsize=7.5, color=INK, ha="left", va="center",
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8, shrinkA=2, shrinkB=2))

    ax.set_xlim(0, 12.5)
    ax.set_ylim(0, ceiling + 0.55)
    ax.set_xticks([0, 2, 4, 6, 8, 10, 12])
    ax.set_yticks(range(0, int(ceiling) + 1))
    ax.set_xlabel("Arrivals per minute", fontsize=8.5, color=INK_2, labelpad=6)
    ax.set_ylabel("Briefs completed on time per minute", fontsize=8.5, color=INK_2, labelpad=6)
    ax.tick_params(colors=MUTED, labelsize=8, length=0, pad=5)
    ax.grid(axis="y", color=GRID, lw=1.0, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)

    legend = ax.legend(loc="upper right", bbox_to_anchor=(1.0, 0.76), frameon=False, fontsize=8, handlelength=2.2,
                       borderaxespad=0.2)
    for text in legend.get_texts():
        text.set_color(INK_2)

    fig.text(0.01, 0.975, "Throughput peaks near the provider ceiling, then collapses", fontsize=10.5,
             fontweight="semibold", color=INK, ha="left", va="top")
    fig.text(0.01, 0.925, "No reuse · 1 subagent per job · 5 searches · 120 s deadline · line = median of 3 seeds, "
             "band = best and worst seed", fontsize=7.5, color=INK_2, ha="left", va="top")
    fig.subplots_adjust(left=0.09, right=0.98, bottom=0.14, top=0.86)

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    render(load_series(args.csv), args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
