"""Runs the control-room page's own script in Node with the events the services really emit.

The page is plain JavaScript inside index.html, so these tests load it as served, feed it events,
and read what it would draw. They skip when Node is not installed.
"""
import json
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from researchdesk import contracts as c
from researchdesk.board.app import create_app

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is needed to run the page's script")

DRIVER = r"""
const fs = require("fs");
const { html, events } = JSON.parse(fs.readFileSync(0, "utf8"));
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const out = {}, els = {};
const el = (id) => (els[id] ||= { value: "", set innerHTML(v) { out[id] = v; }, get innerHTML() { return out[id] ?? ""; },
  set textContent(v) { out[id] = v; }, getContext: () => ({ clearRect() {}, fillRect() {} }) });
global.document = { getElementById: el };
global.EventSource = function () { return {}; };
global.setInterval = () => 0;
const { S, apply, render } = new Function(script + "\n; return { S, apply, render };")();
for (const e of events) apply(e);
render();
console.log(JSON.stringify({ subs: Object.fromEntries(Object.entries(S.jobs.j1?.subs || {}).map(([k, s]) => [k, { k: s.k, done: s.done }])),
  deadline: S.jobs.j1?.deadline, out }));
"""


def page(time_scale: float) -> str:
    return TestClient(create_app(c.Settings(time_scale=time_scale))).get("/").text


def run(events: list[dict], time_scale: float = 1.0) -> dict:
    done = subprocess.run([NODE, "-e", DRIVER], input=json.dumps({"html": page(time_scale), "events": events}),
                          capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def ev(event: str, ts_ms: int = 1000, **kw) -> dict:
    base = dict(ts_ms=ts_ms, run_id="r", client="harness", service="api", event=event, trace_id="j1", job_id="j1",
                subagent_id=None, step=None, worker_id="", key="", fields={}, user="anon")
    return {**base, **kw}


def one_job_with_two_subagents() -> list[dict]:
    # The shapes the Job API, worker and runner emit: subagent_id is a top-level field.
    return [ev("job.submitted", fields={"deadline_ms": 60000}), ev("job.admitted"),
            ev("task.enqueued", subagent_id=0, fields={"queries": ["a", "b"]}),
            ev("task.enqueued", subagent_id=1, fields={"queries": ["c"]}),
            ev("task.claimed", service="worker", subagent_id=0, worker_id="w1"),
            ev("task.step_done", service="runner", subagent_id=0, step=0, fields={"source": "provider"})]


def test_each_subagent_is_one_row_with_its_own_progress():
    got = run(one_job_with_two_subagents())
    assert got["subs"] == {"0": {"k": 2, "done": 1}, "1": {"k": 1, "done": 0}}  # no phantom "null" subagent
    assert "width:50%" in got["out"]["jobs"]  # one of two searches done


def test_the_deadline_is_in_real_time_when_the_clock_is_scaled():
    # deadline_ms is simulated: 60,000 ms at a scale of 0.1 is 6,000 real ms.
    got = run(one_job_with_two_subagents(), time_scale=0.1)
    assert got["deadline"] == 1000 + 6000


def test_calls_per_minute_counts_a_simulated_minute():
    # 200 provider calls 0.3 real seconds apart is 20 a simulated minute at a scale of 0.1.
    served = [ev("provider.served", ts_ms=i * 300, service="provider") for i in range(200)]
    got = run(served, time_scale=0.1)
    assert "<b>20</b>" in got["out"]["strip"] and 'class="tile bad"' not in got["out"]["strip"]


def test_event_text_cannot_inject_html():
    payload = "<img src=x onerror=alert(1)>"
    got = run([ev("task.enqueued", job_id="<b id=evil>", subagent_id=0, fields={"queries": [payload]}),
               ev("job.submitted", job_id="<b id=evil>", fields={"deadline_ms": 1})])
    for panel in ("feed", "jobs"):
        assert "<img" not in got["out"][panel] and "<b id=evil>" not in got["out"][panel], panel
    assert "&lt;img" in got["out"]["feed"]
