"""Regression tests for defects found when reviewing the Job API (PR #26) against the contract.

Each test failed on main before its fix.
"""
import json

import fakeredis
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from researchdesk import contracts as c
from researchdesk.api.app import Deps, create_app
from researchdesk.metrics import events

PLAN = [{"subagent_id": 0, "queries": ["a b", "c d"]}, {"subagent_id": 1, "queries": ["e f"]}]


def body(**kw):
    return {"question": "q", "deadline_ms": 120_000, "client": "test", "run_id": "r1", "plan": PLAN, **kw}


def make(monkeypatch, admit):
    r = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(events, "_redis", lambda settings: r)
    deps = Deps(admit=admit, plan=lambda s, q: [], gather=lambda s, j: None,
                search=lambda s, req, t: c.SearchResult("ok", "k", [1], 5.0, "provider", 0))
    client = TestClient(create_app(c.Settings(run_id="r1", plan_ms=2000, time_scale=0.0001), deps))
    return client, r


def stream(r):
    return [json.loads(f[c.EVENT_FIELD]) for _id, f in r.xrange(c.EVENT_STREAM)]


def test_task_enqueued_carries_subagent_id_at_the_top_level(monkeypatch):
    # The live control room keys each subagent by this field; inside `fields` it saw `null`.
    client, r = make(monkeypatch, lambda s, req: c.AdmitResult(True, 1))
    assert client.post("/jobs", json=body(job_id="j1")).status_code == 202
    enq = [e for e in stream(r) if e["event"] == "task.enqueued"]
    assert sorted(e["subagent_id"] for e in enq) == [0, 1]


def test_a_rejected_job_is_counted_as_rejected_only(monkeypatch):
    client, r = make(monkeypatch, lambda s, req: c.AdmitResult(False, 999, "too_big"))
    assert client.post("/jobs", json=body(job_id="j1")).json()["status"] == "rejected"
    counters = r.hgetall(c.metrics_key("r1"))
    assert counters == {'rd_jobs_total{status="rejected"}': "1"}


def test_an_admitted_job_is_counted_as_admitted(monkeypatch):
    client, r = make(monkeypatch, lambda s, req: c.AdmitResult(True, 1))
    client.post("/jobs", json=body(job_id="j1"))
    assert r.hgetall(c.metrics_key("r1")) == {'rd_jobs_total{status="admitted"}': "1"}


def test_a_failure_after_the_job_id_is_claimed_leaves_nothing_behind(monkeypatch):
    def down(settings, req):
        raise HTTPException(503, "gateway unavailable")

    client, r = make(monkeypatch, down)
    assert client.post("/jobs", json=body(job_id="j1")).status_code == 503
    assert client.get("/jobs/j1").status_code == 404  # was a 500: the job hash held only `status`
    assert not r.exists(c.job_key("j1"))
    # the id is not burned: once the gateway is back, the same job can be submitted
    client2, _ = make(monkeypatch, lambda s, req: c.AdmitResult(True, 1))
    assert client2.post("/jobs", json=body(job_id="j1")).status_code == 202


def test_get_job_during_planning_is_404_not_500(monkeypatch):
    client, r = make(monkeypatch, lambda s, req: c.AdmitResult(True, 1))
    r.hset(c.job_key("j9"), "status", "admitted")  # what a concurrent GET sees between the claim and the full write
    assert client.get("/jobs/j9").status_code == 404
