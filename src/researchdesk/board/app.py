"""Live control room (contract section 9, task M12). It only displays events from rd:events;
it never writes to Redis. GET / is the page, GET /events/stream is a server-sent-events feed."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

from researchdesk import contracts as c
from researchdesk.metrics import events

PAGE = Path(__file__).with_name("index.html")


def start_id(r, since: str, tail: int) -> str:
    """Where to start reading: `since` if given, else the id `tail` events back, else only new events."""
    if since:
        return since
    if tail > 0:
        recent = r.xrevrange(c.EVENT_STREAM, count=tail)
        if recent:
            return recent[-1][0]
        return "0"
    return "$"


def stream(r, last: str, limit: int | None):
    sent = 0
    while limit is None or sent < limit:
        got = r.xread({c.EVENT_STREAM: last}, count=200, block=1000)
        if not got:
            yield ": keepalive\n\n"
            continue
        for entry_id, f in got[0][1]:
            last = entry_id
            sent += 1
            yield f"id: {entry_id}\ndata: {f[c.EVENT_FIELD]}\n\n"
            if limit is not None and sent >= limit:
                return


def create_app(settings: c.Settings) -> FastAPI:
    app = FastAPI(title="researchdesk-board")

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "board", "contract_version": c.CONTRACT_VERSION}

    @app.get("/", response_class=HTMLResponse)
    def page():
        # The page needs RD_TIME_SCALE: event times are real milliseconds, while deadlines and the
        # 20-calls-a-minute limit are in simulated time. Unreplaced, the page falls back to 1.
        return PAGE.read_text().replace("__TIME_SCALE__", str(settings.time_scale))

    @app.get("/events/stream")
    def events_stream(since: str = "", tail: int = 500, max: int | None = None):
        r = events.client(settings)
        begin = start_id(r, since, tail)
        # xread returns entries strictly AFTER the id; step one back so `tail` includes its first event
        if begin not in ("$", "0"):
            ms, _, seq = begin.partition("-")
            begin = f"{ms}-{int(seq) - 1}" if int(seq) > 0 else f"{int(ms) - 1}-18446744073709551615"
        return StreamingResponse(stream(r, begin, max), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app


app = create_app(c.Settings.from_env(os.environ))
