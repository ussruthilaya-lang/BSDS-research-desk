import fakeredis
from fastapi.testclient import TestClient

from researchdesk import contracts as c
from researchdesk.api.app import Deps, create_app
from researchdesk.metrics import events
from researchdesk.workflow import stubs, worker


def test_one_job_end_to_end_with_stub_runner(monkeypatch):
    """POST /jobs -> task on rd:tasks -> worker runs it -> stub gather writes the final status."""
    r = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(events, "_redis", lambda settings: r)
    s = c.Settings(run_id="r1", time_scale=0.001, plan_ms=0, synth_ms=0, think_ms=0)
    admit = lambda settings, req: c.AdmitResult(True, 0)
    client = TestClient(create_app(s, Deps(admit=admit)))  # default gather is the stub gather
    plan = [{"subagent_id": i, "queries": [f"q{i} a", f"q{i} b"]} for i in range(2)]
    res = client.post("/jobs", json={"question": "q", "deadline_ms": 600_000, "client": "test",
                                     "run_id": "r1", "plan": plan, "job_id": "j1", "gather": "wait_all"})
    assert res.status_code == 202

    dispatch = lambda settings, req: c.DispatchResult("ok", req.key, [1], 0.0, 1.0, 0, request_id="p")
    run = lambda settings, task, wid: stubs.run_subagent(settings, task, wid, dispatch=dispatch)
    while worker.process_one(s, "w1", stubs.claim, run, stubs.heartbeat, stubs.ack):
        pass

    import time
    for _ in range(100):  # the gather thread polls every 50 ms
        view = client.get("/jobs/j1").json()
        if view["status"] in ("on_time", "late"):
            break
        time.sleep(0.05)
    assert view["status"] == "on_time" and view["completeness"] == 1.0
    assert [s["status"] for s in view["subagents"]] == ["done", "done"]
    assert view["subagents"][0]["paper_ids"] == [[1], [1]]
