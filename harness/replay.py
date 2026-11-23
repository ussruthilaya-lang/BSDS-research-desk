"""Replay harness (contract section 12): posts a workload file's jobs at their scaled arrival times,
waits for every job to finish, and appends one row to the results CSV.

    python -m harness.replay workload.json --run-id e1-w4-r12-s0 --setting workers=4,rate=12 --seed 0 \
        --out results/e1.csv [--scale 0.1] [--api URL] [--provider URL] [--redis URL]

Every number comes from the deployed system (Mode A, client `harness`); nothing is computed from
the simulator.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import redis

from researchdesk import contracts as c

FINAL = {s.value for s in c.FINAL_JOB_STATUSES}


def post_delay_s(job: c.WorkloadJob, time_scale: float) -> float:
    """Real seconds after the start at which to post the job: arrival_s x 1000 x scale ms."""
    return job.arrival_s * time_scale


def job_request(job: c.WorkloadJob, run_id: str) -> dict:
    # The id is prefixed with the run so the same workload can be replayed (other seeds, settings)
    # on one Redis without a 409 for a duplicate job_id.
    return c.JobRequest(
        question=f"workload job {job.job_id}", deadline_ms=int(job.deadline_s * 1000), client=c.Client.HARNESS.value,
        run_id=run_id, plan=job.plan, job_id=f"{run_id}-{job.job_id}").to_dict()


def p95(values: list[float]) -> float:
    """Nearest-rank 95th percentile; NaN when empty."""
    if not values:
        return math.nan
    ordered = sorted(values)
    return ordered[max(math.ceil(0.95 * len(ordered)) - 1, 0)]


def summarize(views: list[dict], events: list[dict], stats: dict, *, horizon_s: float, time_scale: float,
              run_id: str, setting: str, seed: int) -> dict:
    """One CSV row (every column of contract section 12) from final job views, the run's events and
    the provider's /stats. `horizon_s` is the run length in simulated seconds.

    completeness_mean is the mean completeness of jobs that wrote a brief (on_time or late).
    """
    def correct(v):
        return v["status"] == "on_time" and v["completeness"] > 0 and not any(
            s["stale_steps"] for s in v["subagents"])

    good = [v for v in views if correct(v)]
    count = lambda status: sum(v["status"] == status for v in views)
    minutes = horizon_s / 60.0
    calls = stats["calls"]
    good_ids = {v["job_id"] for v in good}
    used = {e["fields"].get("request_id") for e in events
            if e["event"] == "task.step_done" and e["job_id"] in good_ids and e["fields"].get("request_id")}
    written = [v["completeness"] for v in views if v["status"] in ("on_time", "late")]
    latencies = [(v["finished_at_ms"] - v["created_at_ms"]) / time_scale / 1000 for v in good]
    depths = [e["fields"]["depth"] for e in events if e["event"] == "gateway.queued"]
    row = {
        "run_id": run_id, "setting": setting, "seed": seed,
        "briefs_per_min": len(good) / minutes,
        "complete_briefs_per_min": sum(v["completeness"] == 1 for v in good) / minutes,
        "on_time_correct": len(good),
        "wrong_briefs": sum(v["status"] == "on_time" and not correct(v) for v in views),
        "late": count("late"), "expired": count("expired"), "rejected": count("rejected"),
        "failed": count("failed"), "upstream_calls": calls,
        "calls_per_brief": calls / len(good) if good else math.nan,
        "p95_latency_s": p95(latencies),
        "completeness_mean": sum(written) / len(written) if written else math.nan,
        "cache_hits": sum(e["event"] == "search.cache_hit" for e in events),
        "merged": sum(e["event"] == "search.merged" for e in events),
        "wasted_calls": calls - len(used),
        "max_queue_depth": max(depths, default=0),
        "violations": stats["overlap_violations"] + stats["pacing_violations"],
    }
    assert tuple(row) == c.HARNESS_CSV_COLUMNS
    return row


def read_events(r: redis.Redis, run_id: str) -> list[dict]:
    out = []
    for _id, f in r.xrange(c.EVENT_STREAM):
        rec = json.loads(f[c.EVENT_FIELD])
        if rec["run_id"] == run_id:
            out.append(rec)
    return out


def _emit(r: redis.Redis, run_id: str, name: str, **fields) -> None:
    rec = c.EventRecord(ts_ms=c.redis_time_to_ms(r.time()), run_id=run_id, client=c.Client.HARNESS.value,
                        service="harness", event=name, fields=fields)
    print(rec.to_json(), flush=True)
    r.xadd(c.EVENT_STREAM, {c.EVENT_FIELD: rec.to_json()}, maxlen=c.EVENT_STREAM_MAXLEN, approximate=True)


def replay(workload: c.WorkloadFile, *, api: str, provider: str, r: redis.Redis, run_id: str, setting: str,
           seed: int, time_scale: float, out: Path) -> dict:
    http = httpx.Client(timeout=30)
    http.post(f"{provider}/reset", json={"run_id": run_id}).raise_for_status()  # zero the violation counters
    _emit(r, run_id, "run.started", setting=setting, seed=seed, n_jobs=len(workload.jobs))
    start = time.monotonic()

    def post(job: c.WorkloadJob):
        time.sleep(max(post_delay_s(job, time_scale) - (time.monotonic() - start), 0))
        res = http.post(f"{api}/jobs", json=job_request(job, run_id))
        res.raise_for_status()
        return res.json()["job_id"]

    with ThreadPoolExecutor(max_workers=max(len(workload.jobs), 1)) as pool:  # POST /jobs blocks for plan time
        ids = list(pool.map(post, workload.jobs))
    last_end = max(j.arrival_s + j.deadline_s for j in workload.jobs)
    give_up = start + last_end * time_scale + 60  # a stuck job must not hang the run forever
    views: dict[str, dict] = {}
    while len(views) < len(ids) and time.monotonic() < give_up:
        for jid in ids:
            if jid not in views:
                v = http.get(f"{api}/jobs/{jid}").json()
                if v["status"] in FINAL:
                    views[jid] = v
        time.sleep(0.5)
    horizon = float(workload.params.get("duration_s", last_end))
    stats = http.get(f"{provider}/stats", params={"run_id": run_id}).json()
    row = summarize(list(views.values()), read_events(r, run_id), stats, horizon_s=horizon,
                    time_scale=time_scale, run_id=run_id, setting=setting, seed=seed)
    new = not out.exists()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=c.HARNESS_CSV_COLUMNS)
        if new:
            w.writeheader()
        w.writerow(row)
    _emit(r, run_id, "run.finished", csv_path=str(out), jobs_unfinished=len(ids) - len(views))
    return row


def main() -> None:
    env = c.Settings.from_env(os.environ)
    p = argparse.ArgumentParser()
    p.add_argument("workload")
    p.add_argument("--run-id", required=True)
    p.add_argument("--setting", required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--scale", type=float, default=env.time_scale)
    p.add_argument("--api", default=env.api_url)
    p.add_argument("--provider", default=env.provider_url)
    p.add_argument("--redis", default=env.redis_url)
    a = p.parse_args()
    workload = c.WorkloadFile.from_json(Path(a.workload).read_text())
    r = redis.Redis.from_url(a.redis, decode_responses=True)
    print(replay(workload, api=a.api, provider=a.provider, r=r, run_id=a.run_id, setting=a.setting,
                 seed=a.seed, time_scale=a.scale, out=Path(a.out)))


if __name__ == "__main__":
    main()
