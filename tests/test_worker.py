import json

import fakeredis
import pytest

from researchdesk import contracts as c
from researchdesk.metrics import events
from researchdesk.workflow import stubs, worker


@pytest.fixture
def r(monkeypatch):
    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(events, "_redis", lambda settings: client)
    return client


def enqueue(r, job="j1", sub=0, queries=("a b", "c d")):
    r.hset(c.subagent_key(job, sub), mapping={"status": "queued", "steps_done": 0, "k": len(queries),
                                              "stale_steps": 0, "worker_id": ""})
    r.xadd(c.TASK_STREAM, {"job_id": job, "subagent_id": sub, "queries": json.dumps(list(queries)),
                           "deadline_at_ms": 9_999_999_999_999, "trace_id": job, "client": "test",
                           "user": "anon", "run_id": "r1", "attempt": 0})


def ok_dispatch(settings, req):
    return c.DispatchResult("ok", req.key, [1, 2], 0.0, 1.0, corpus_version=0, request_id="p1")


def test_stub_lease_claims_then_acks(r):
    s = c.Settings(run_id="r1")
    enqueue(r)
    entry_id, task = stubs.claim(s, "w1")
    assert task["job_id"] == "j1" and stubs.claim(s, "w1") is None
    stubs.ack(s, entry_id)
    assert r.xpending(c.TASK_STREAM, c.TASK_GROUP)["pending"] == 0


def test_stub_runner_writes_checkpoints_and_finishes(r):
    s = c.Settings(run_id="r1", time_scale=0.0001)
    enqueue(r)
    _, task = stubs.claim(s, "w1")
    assert stubs.run_subagent(s, task, "w1", dispatch=ok_dispatch) == "done"
    assert r.hget(c.subagent_key("j1", 0), "status") == "done"
    assert r.hget(c.subagent_key("j1", 0), "steps_done") == "2"
    assert json.loads(r.get(c.checkpoint_key("j1", 0, 1)))["paper_ids"] == [1, 2]


def test_stub_runner_fails_the_subagent_on_a_dropped_search(r):
    s = c.Settings(run_id="r1", time_scale=0.0001)
    enqueue(r)
    _, task = stubs.claim(s, "w1")
    drop = lambda settings, req: c.DispatchResult("dropped", req.key, [], 0.0, 0.0, reason="queue_full")
    assert stubs.run_subagent(s, task, "w1", dispatch=drop) == "failed"
    assert r.hget(c.subagent_key("j1", 0), "status") == "failed"


def test_process_one_claims_runs_acks_and_counts(r):
    s = c.Settings(run_id="r1", time_scale=0.0001)
    enqueue(r)
    assert worker.process_one(s, "w1", stubs.claim, lambda *a: "done", stubs.heartbeat, stubs.ack) is True
    assert worker.process_one(s, "w1", stubs.claim, lambda *a: "done", stubs.heartbeat, stubs.ack) is False
    assert r.xpending(c.TASK_STREAM, c.TASK_GROUP)["pending"] == 0
    assert r.hget(c.metrics_key("r1"), 'rd_tasks_total{status="done"}') == "1"
    names = [json.loads(e[1][c.EVENT_FIELD])["event"] for e in r.xrange(c.EVENT_STREAM)]
    assert "task.claimed" in names


def test_a_crashing_runner_leaves_the_task_pending(r):
    s = c.Settings(run_id="r1", time_scale=0.0001)
    enqueue(r)

    def boom(*a):
        raise RuntimeError("worker died")

    with pytest.raises(RuntimeError):
        worker.process_one(s, "w1", stubs.claim, boom, stubs.heartbeat, stubs.ack)
    assert r.xpending(c.TASK_STREAM, c.TASK_GROUP)["pending"] == 1  # not acked: a lease can reclaim it
