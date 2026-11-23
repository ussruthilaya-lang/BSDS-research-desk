import json
import threading

import fakeredis
import pytest
from fastapi.testclient import TestClient

from researchdesk import contracts as c
from researchdesk.api.app import Deps, create_app
from researchdesk.metrics import events

PLAN = [{"subagent_id": 0, "queries": ["a b", "c d"]}, {"subagent_id": 1, "queries": ["e f", "g h", "i j"]}]


def body(**kw):
    return {"question": "q", "deadline_ms": 120_000, "client": "test", "run_id": "r1", "plan": PLAN, **kw}


@pytest.fixture
def env(monkeypatch):
    r = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(events, "_redis", lambda settings: r)
    calls = {"admit": [], "plan": [], "gather": []}
    gathered = threading.Event()

    def admit(settings, req):
        calls["admit"].append(req)
        return calls.get("admit_result") or c.AdmitResult(admitted=True, estimated_ms=1000)

    def plan(settings, question):
        calls["plan"].append(question)
        return [c.SubagentPlan(subagent_id=0, queries=["x y"])]

    def gather(settings, job_id):
        calls["gather"].append(job_id)
        gathered.set()

    def search(settings, req, trace_id):
        return calls.get("search_result") or c.SearchResult("ok", "k", [1], 5.0, "provider", 0)

    settings = c.Settings(run_id="r1", plan_ms=2000, time_scale=0.0001)
    client = TestClient(create_app(settings, Deps(admit=admit, plan=plan, gather=gather, search=search)))
    return client, r, calls, gathered


def test_post_jobs_enqueues_one_task_per_subagent(env):
    client, r, calls, gathered = env
    res = client.post("/jobs", json=body(job_id="j1"))
    assert res.status_code == 202
    assert res.json() == {"job_id": "j1", "trace_id": "j1", "status": "admitted"}
    tasks = r.xrange(c.TASK_STREAM)
    assert len(tasks) == 2
    f = tasks[1][1]
    assert (f["job_id"], f["subagent_id"], json.loads(f["queries"])) == ("j1", "1", ["e f", "g h", "i j"])
    assert {"deadline_at_ms", "trace_id", "client", "user", "run_id", "attempt"} <= set(f)
    assert r.hget(c.job_key("j1"), "status") == "admitted"
    assert gathered.wait(2) and calls["gather"] == ["j1"]


def test_admit_gets_plan_shape_and_deadline_minus_plan_time(env):
    client, _, calls, _ = env
    client.post("/jobs", json=body(job_id="j1"))
    req = calls["admit"][0]
    assert (req.n_subagents, req.k, req.expected_hit_rate) == (2, 3, 0)
    assert req.deadline_ms == 120_000 - 2000


def test_missing_plan_calls_the_lead(env):
    client, _, calls, _ = env
    b = body(); del b["plan"]
    assert client.post("/jobs", json=b).status_code == 202
    assert calls["plan"] == ["q"]


def test_admission_off_skips_admit(monkeypatch):
    r = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(events, "_redis", lambda settings: r)
    asked = []
    deps = Deps(admit=lambda s, q: asked.append(q), plan=None, gather=lambda s, j: None, search=None)
    client = TestClient(create_app(c.Settings(run_id="r1", admission=False, plan_ms=0), deps))
    assert client.post("/jobs", json=body(job_id="j1")).status_code == 202
    assert asked == []


def test_rejected_job_is_final_and_enqueues_nothing(env):
    client, r, calls, _ = env
    calls["admit_result"] = c.AdmitResult(admitted=False, estimated_ms=999999, reason="admission_rejected")
    res = client.post("/jobs", json=body(job_id="j1"))
    assert res.status_code == 202 and res.json()["status"] == "rejected"
    assert r.xlen(c.TASK_STREAM) == 0
    view = client.get("/jobs/j1").json()
    assert view["status"] == "rejected" and view["finished_at_ms"] is not None


def test_duplicate_job_id_is_409(env):
    client, *_ = env
    assert client.post("/jobs", json=body(job_id="j1")).status_code == 202
    assert client.post("/jobs", json=body(job_id="j1")).status_code == 409


@pytest.mark.parametrize("bad", [
    {"question": None}, {"client": "nope"}, {"user": "Bad User"}, {"deadline_ms": 0},
    {"gather": "sometimes"}, {"extra": 1}, {"plan": []}, {"plan": [{"subagent_id": 0, "queries": []}]},
])
def test_invalid_input_is_400(env, bad):
    client, *_ = env
    b = body(); b.update(bad)
    if b.get("question") is None:
        del b["question"]
    assert client.post("/jobs", json=b).status_code == 400


def test_unknown_job_is_404(env):
    assert env[0].get("/jobs/nope").status_code == 404


def test_job_view_reads_checkpoints_in_step_order(env):
    client, r, *_ = env
    client.post("/jobs", json=body(job_id="j1"))
    r.hset(c.subagent_key("j1", 0), mapping={"status": "done", "steps_done": 2})
    r.set(c.checkpoint_key("j1", 0, 1), json.dumps({"paper_ids": [9]}))
    r.set(c.checkpoint_key("j1", 0, 0), json.dumps({"paper_ids": [7, 8]}))
    sub = client.get("/jobs/j1").json()["subagents"][0]
    assert sub["status"] == "done" and sub["k"] == 2 and sub["paper_ids"] == [[7, 8], [9]]
    assert client.get("/jobs/j1").json()["subagents"][1]["status"] == "queued"


def test_events_and_trace(env):
    client, r, *_ = env
    client.post("/jobs", json=body(job_id="j1"))
    names = [json.loads(e[1][c.EVENT_FIELD])["event"] for e in r.xrange(c.EVENT_STREAM)]
    assert names == ["job.submitted", "job.planned", "job.admitted"] + ["task.enqueued"] * 2
    trace = client.get("/jobs/j1/trace").json()
    assert [e["event"] for e in trace] == names


def test_search_status_codes(env):
    client, _, calls, _ = env
    b = {"query": "x", "deadline_ms": 1000, "client": "test", "run_id": "r1"}
    assert client.post("/search", json=b).status_code == 200
    calls["search_result"] = c.SearchResult("dropped", "k", [], 0.0, reason="queue_full")
    assert client.post("/search", json=b).status_code == 503
    calls["search_result"] = c.SearchResult("dropped", "k", [], 0.0, reason="user_quota")
    assert client.post("/search", json=b).status_code == 429
    assert client.post("/search", json={"query": "x"}).status_code == 400


def test_metrics_text_carries_run_id(env):
    client, *_ = env
    client.post("/jobs", json=body(job_id="j1"))
    text = client.get("/metrics").text
    assert 'rd_jobs_total{run_id="r1",status="admitted"} 1' in text
