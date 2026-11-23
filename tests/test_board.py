import json

import fakeredis
from fastapi.testclient import TestClient

from researchdesk import contracts as c
from researchdesk.board.app import create_app
from researchdesk.metrics import events


def make(monkeypatch, n):
    r = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(events, "_redis", lambda settings: r)
    for i in range(n):
        rec = c.EventRecord(ts_ms=i, run_id="r", client="test", service="api", event="job.submitted", job_id=f"j{i}")
        r.xadd(c.EVENT_STREAM, {c.EVENT_FIELD: rec.to_json()})
    return TestClient(create_app(c.Settings())), r


def data_lines(text):
    return [json.loads(x[5:]) for x in text.splitlines() if x.startswith("data:")]


def test_stream_replays_the_tail_in_order(monkeypatch):
    client, _ = make(monkeypatch, 5)
    got = data_lines(client.get("/events/stream?tail=3&max=3").text)
    assert [e["job_id"] for e in got] == ["j2", "j3", "j4"]


def test_stream_replays_everything_when_tail_is_larger_than_the_stream(monkeypatch):
    client, _ = make(monkeypatch, 2)
    assert len(data_lines(client.get("/events/stream?tail=500&max=2").text)) == 2


def test_page_has_every_panel_and_health_works(monkeypatch):
    client, _ = make(monkeypatch, 0)
    html = client.get("/").text
    for panel in ("violations", "queue depth", "Jobs", "Gateway timeline", "Workers and leases", "Users", "Event feed", "Run"):
        assert panel in html
    assert client.get("/health").json()["service"] == "board"


def test_board_never_writes_to_redis(monkeypatch):
    client, r = make(monkeypatch, 2)
    before = r.xlen(c.EVENT_STREAM)
    client.get("/events/stream?tail=2&max=2")
    client.get("/")
    assert r.xlen(c.EVENT_STREAM) == before
