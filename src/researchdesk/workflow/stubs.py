"""Stand-ins for the lease and runner functions (contract section 8) until the real ones land.

The lease stub is a plain consumer group with no reclaim; the runner stub dispatches each query
straight to the gateway with no cache and no merging. Same names and shapes as the real ones.
"""
from __future__ import annotations

import json
import time
from typing import Callable, Optional

import httpx
import redis

from researchdesk import contracts as c
from researchdesk.metrics import events


def _ensure_group(r: redis.Redis) -> None:
    try:
        r.xgroup_create(c.TASK_STREAM, c.TASK_GROUP, id="0", mkstream=True)
    except redis.ResponseError as err:
        if "BUSYGROUP" not in str(err):
            raise


def claim(settings: c.Settings, worker_id: str) -> Optional[tuple[str, dict]]:
    r = events.client(settings)
    _ensure_group(r)
    got = r.xreadgroup(c.TASK_GROUP, worker_id, {c.TASK_STREAM: ">"}, count=1)
    if not got:
        return None
    entry_id, fields = got[0][1][0]
    return entry_id, fields


def heartbeat(settings: c.Settings, worker_id: str, entry_id: str) -> None:
    px = max(int(c.to_real_ms(settings.lease_ms, settings.time_scale)), 1)
    events.client(settings).set(c.heartbeat_key(worker_id), entry_id, px=px)


def ack(settings: c.Settings, entry_id: str) -> None:
    events.client(settings).xack(c.TASK_STREAM, c.TASK_GROUP, entry_id)


def _gateway_dispatch(settings: c.Settings, req: c.DispatchRequest) -> c.DispatchResult:
    timeout = c.to_real_ms(req.deadline_ms, settings.time_scale) / 1000 + 5
    return c.DispatchResult.from_dict(
        httpx.post(f"{settings.gateway_url}/dispatch", json=req.to_dict(), timeout=timeout).json())


def run_subagent(settings: c.Settings, task: dict, worker_id: str,
                 dispatch: Callable = _gateway_dispatch) -> str:
    """Run every query of one task in order: dispatch, checkpoint, think. Returns a task status."""
    r = events.client(settings)
    job_id, sub = task["job_id"], int(task["subagent_id"])
    key = c.subagent_key(job_id, sub)
    r.hset(key, mapping={"status": c.TaskStatus.RUNNING.value, "worker_id": worker_id})
    for step, query in enumerate(json.loads(task["queries"])):
        remaining = int(c.to_sim_ms(int(task["deadline_at_ms"]) - c.redis_time_to_ms(r.time()), settings.time_scale))
        res = dispatch(settings, c.DispatchRequest(
            key=c.query_key(query), deadline_ms=max(remaining, 0), client=task["client"], run_id=task["run_id"],
            trace_id=task["trace_id"], attempt=int(task["attempt"]), job_id=job_id, subagent_id=sub,
            user=task["user"]))
        if res.status != "ok":
            r.hset(key, "status", c.TaskStatus.FAILED.value)
            return c.TaskStatus.FAILED.value
        r.set(c.checkpoint_key(job_id, sub, step), json.dumps({
            "paper_ids": res.paper_ids, "corpus_version": res.corpus_version, "source": "provider",
            "stale": False, "request_id": res.request_id}), nx=True)
        r.hset(key, "steps_done", step + 1)
        time.sleep(c.to_real_ms(settings.think_ms, settings.time_scale) / 1000)
    r.hset(key, "status", c.TaskStatus.DONE.value)
    return c.TaskStatus.DONE.value
