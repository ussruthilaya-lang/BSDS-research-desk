"""Stand-ins for the cross-lane functions the Job API calls, until the real ones land.

Used only when `researchdesk.workflow.lead` / `runner` cannot be imported. Same names and shapes
as contract section 8, so the Job API never changes when the real ones arrive.
"""
from __future__ import annotations

import time

from researchdesk import contracts as c
from researchdesk.metrics import events


def plan(settings: c.Settings, question: str) -> list[c.SubagentPlan]:
    return [c.SubagentPlan(i, [f"{question} {i}-{j}" for j in range(3)]) for i in range(3)]


def search(settings: c.Settings, req: c.SearchRequest, trace_id: str) -> c.SearchResult:
    return c.SearchResult("dropped", "", [], 0.0, reason=c.DropReason.PROVIDER_ERROR.value)


def final_status(done: int, failed: int, n: int, finished_at_ms: int, deadline_at_ms: int) -> str:
    """Contract section 6, final-status rules."""
    if done == 0:
        return c.JobStatus.FAILED.value if failed == n else c.JobStatus.EXPIRED.value
    return c.JobStatus.ON_TIME.value if finished_at_ms <= deadline_at_ms else c.JobStatus.LATE.value


def gather(settings: c.Settings, job_id: str, poll_s: float = 0.05) -> None:
    """Stub of lead.gather: wait per the job's policy, then write completeness and final status."""
    r = events.client(settings)
    job = r.hgetall(c.job_key(job_id))
    n, deadline_at = int(job["n_subagents"]), int(job["deadline_at_ms"])
    stop_at = deadline_at - int(c.to_real_ms(settings.gather_margin_ms, settings.time_scale))
    partial = job["gather"] == c.GatherPolicy.DEADLINE_PARTIAL.value

    def counts():
        st = [r.hget(c.subagent_key(job_id, i), "status") for i in range(n)]
        return st.count(c.TaskStatus.DONE.value), st.count(c.TaskStatus.FAILED.value)

    while True:
        done, failed = counts()
        if done + failed == n or (partial and c.redis_time_to_ms(r.time()) >= stop_at):
            break
        time.sleep(poll_s)
    time.sleep(c.to_real_ms(settings.synth_ms, settings.time_scale) / 1000)
    now = c.redis_time_to_ms(r.time())
    status = final_status(done, failed, n, now, deadline_at)
    r.hset(c.job_key(job_id), mapping={
        "status": status, "done": done, "failed": failed, "completeness": done / n, "finished_at_ms": now})
    base = dict(ts_ms=now, run_id=job["run_id"], client=job["client"], service="lead",
                trace_id=job_id, job_id=job_id, user=job["user"])
    events.emit(settings, c.EventRecord(event="job.gathered", fields={
        "policy": job["gather"], "completeness": done / n}, **base))
    events.emit(settings, c.EventRecord(event="job.finished", fields={
        "status": status, "completeness": done / n,
        "latency_ms": c.to_sim_ms(now - int(job["created_at_ms"]), settings.time_scale)}, **base))
    events.count(settings, "rd_jobs_total", {"status": status})
