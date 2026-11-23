import json

import fakeredis

from researchdesk import contracts as c
from researchdesk.metrics import timeline


def put(r, ts, event, trace="j1", **kw):
    rec = c.EventRecord(ts_ms=ts, run_id="r", client="test", service="api", event=event, trace_id=trace, **kw)
    r.xadd(c.EVENT_STREAM, {c.EVENT_FIELD: rec.to_json()})


def test_timeline_is_sorted_filtered_and_relative():
    r = fakeredis.FakeRedis(decode_responses=True)
    put(r, 1500, "job.admitted", fields={"estimated_ms": 9})
    put(r, 1000, "job.submitted")
    put(r, 1200, "job.submitted", trace="other")
    out = timeline.render(timeline.load(r, "j1")).splitlines()
    assert len(out) == 2
    assert "+       0 ms" in out[0] and "job.submitted" in out[0]
    assert "+     500 ms" in out[1] and "estimated_ms=9" in out[1]


def test_empty_timeline_says_so():
    assert "no events" in timeline.render([])


def test_dashboard_only_queries_contract_metrics():
    import re
    from pathlib import Path
    d = json.loads((Path(__file__).parent.parent / "config/grafana/dashboard.json").read_text())
    used = {m for p in d["panels"] for t in p["targets"] for m in re.findall(r"rd_[a-z_]+", t["expr"])}
    assert used and used <= set(c.METRICS)
