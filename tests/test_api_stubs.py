import fakeredis
import pytest

from researchdesk import contracts as c
from researchdesk.api import stubs
from researchdesk.metrics import events


@pytest.mark.parametrize("done,failed,finished,expect", [
    (0, 2, 10, "failed"),     # nothing done and every subagent failed
    (0, 1, 10, "expired"),    # nothing done, one still unfinished
    (1, 1, 10, "on_time"),    # something done by the deadline
    (2, 0, 11, "late"),       # done, but after the deadline
])
def test_final_status_rules(done, failed, finished, expect):
    assert stubs.final_status(done, failed, 2, finished, deadline_at_ms=10) == expect


def test_gather_waits_for_all_then_writes_final_status(monkeypatch):
    r = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(events, "_redis", lambda settings: r)
    s = c.Settings(run_id="r1", synth_ms=0, time_scale=1.0)
    now = c.redis_time_to_ms(r.time())
    r.hset(c.job_key("j"), mapping={"n_subagents": 2, "deadline_at_ms": now + 60_000, "created_at_ms": now,
                                    "gather": "wait_all", "client": "test", "user": "anon", "run_id": "r1"})
    r.hset(c.subagent_key("j", 0), "status", "done")
    r.hset(c.subagent_key("j", 1), "status", "failed")
    stubs.gather(s, "j", poll_s=0.01)
    job = r.hgetall(c.job_key("j"))
    assert job["status"] == "on_time" and float(job["completeness"]) == 0.5
    assert r.hget(c.metrics_key("r1"), 'rd_jobs_total{status="on_time"}') == "1"
