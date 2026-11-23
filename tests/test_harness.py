import math

from harness import replay
from researchdesk import contracts as c


def view(job_id, status, completeness=1.0, created=0, finished=60_000, stale=0):
    return {"job_id": job_id, "status": status, "completeness": completeness, "created_at_ms": created,
            "finished_at_ms": finished, "subagents": [{"stale_steps": stale}]}


def ev(event, job_id="", **fields):
    return {"event": event, "job_id": job_id, "fields": fields}


def summarize(views, events, calls=10, violations=(0, 0), horizon=60.0, scale=1.0):
    stats = {"calls": calls, "overlap_violations": violations[0], "pacing_violations": violations[1]}
    return replay.summarize(views, events, stats, horizon_s=horizon, time_scale=scale,
                            run_id="r", setting="s", seed=1)


def test_row_has_every_contract_column_in_order():
    row = summarize([view("a", "on_time")], [])
    assert tuple(row) == c.HARNESS_CSV_COLUMNS


def test_correct_is_on_time_with_no_stale_steps():
    row = summarize([view("a", "on_time"), view("b", "on_time", stale=1), view("c", "late"),
                     view("d", "expired", 0), view("e", "rejected", 0), view("f", "failed", 0)], [])
    assert (row["on_time_correct"], row["wrong_briefs"], row["late"], row["expired"], row["rejected"],
            row["failed"]) == (1, 1, 1, 1, 1, 1)


def test_partial_briefs_count_in_briefs_per_min_but_not_complete():
    row = summarize([view("a", "on_time", 1.0), view("b", "on_time", 0.5)], [], horizon=120.0)
    assert row["briefs_per_min"] == 1.0 and row["complete_briefs_per_min"] == 0.5


def test_violations_and_calls_per_brief():
    row = summarize([view("a", "on_time"), view("b", "on_time")], [], calls=10, violations=(1, 2))
    assert row["violations"] == 3 and row["calls_per_brief"] == 5 and row["upstream_calls"] == 10


def test_calls_per_brief_is_nan_without_good_briefs():
    assert math.isnan(summarize([view("a", "late")], [])["calls_per_brief"])


def test_latency_is_simulated_seconds():
    row = summarize([view("a", "on_time", created=0, finished=6_000)], [], scale=0.1)
    assert row["p95_latency_s"] == 60.0


def test_event_counts_and_max_queue_depth():
    events = [ev("search.cache_hit"), ev("search.cache_hit"), ev("search.merged"),
              ev("gateway.queued", depth=3), ev("gateway.queued", depth=7), ev("gateway.queued", depth=2)]
    row = summarize([], events)
    assert (row["cache_hits"], row["merged"], row["max_queue_depth"]) == (2, 1, 7)


def test_wasted_calls_counts_distinct_request_ids_used_by_good_briefs():
    events = [ev("task.step_done", "a", request_id="p1"), ev("task.step_done", "a", request_id="p2"),
              ev("task.step_done", "a", request_id="p2"),   # a cache hit reusing p2: counts once
              ev("task.step_done", "b", request_id="p3")]   # belongs to a late job: not used
    row = summarize([view("a", "on_time"), view("b", "late")], events, calls=5)
    assert row["wasted_calls"] == 5 - 2


def test_request_and_delay_follow_section_12():
    job = c.WorkloadJob("j1", arrival_s=30.0, deadline_s=120.0, plan=[c.SubagentPlan(0, ["a b"])])
    assert replay.post_delay_s(job, 0.1) == 3.0  # arrival_s * RD_TIME_SCALE
    body = replay.job_request(job, "run7")
    assert body["deadline_ms"] == 120_000 and body["client"] == "harness" and body["job_id"] == "run7-j1"
    assert body["plan"] == [{"subagent_id": 0, "queries": ["a b"]}]
