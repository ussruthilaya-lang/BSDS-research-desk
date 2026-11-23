import json

import fakeredis
import pytest
import redis

from researchdesk import contracts as c
from researchdesk.metrics import events


@pytest.fixture
def r(monkeypatch):
    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(events, "_redis", lambda settings: client)
    return client


def _record(**kw):
    base = dict(ts_ms=1, run_id="r1", client="test", service="api", event="job.submitted")
    return c.EventRecord(**{**base, **kw})


def test_emit_adds_one_stream_entry_that_parses(r):
    rec = _record(job_id="j1", fields={"n_subagents": 3})
    events.emit(c.Settings(), rec)
    entries = r.xrange(c.EVENT_STREAM)
    assert len(entries) == 1
    assert c.EventRecord.from_json(entries[0][1][c.EVENT_FIELD]) == rec


def test_emit_prints_one_json_line(r, capsys):
    events.emit(c.Settings(), _record())
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["event"] == "job.submitted"


def test_emit_still_logs_when_redis_is_down(monkeypatch, capsys):
    def boom(settings):
        raise redis.ConnectionError("redis down")

    monkeypatch.setattr(events, "_redis", boom)
    events.emit(c.Settings(), _record())  # must not raise: a missing event is not worth a crash
    assert "job.submitted" in capsys.readouterr().out


def test_count_adds_the_amount(r):
    s = c.Settings(run_id="r1")
    events.count(s, "rd_tasks_total", {"status": "done"})
    events.count(s, "rd_tasks_total", {"status": "done"}, amount=4)
    events.count(s, "rd_tasks_total", {"status": "failed"})
    h = r.hgetall(c.metrics_key("r1"))
    assert h['rd_tasks_total{status="done"}'] == "5"
    assert h['rd_tasks_total{status="failed"}'] == "1"


def test_count_rejects_unknown_metric_and_wrong_labels(r):
    s = c.Settings()
    with pytest.raises(ValueError):
        events.count(s, "rd_nope_total", {})
    with pytest.raises(ValueError):
        events.count(s, "rd_tasks_total", {"wrong": "x"})
