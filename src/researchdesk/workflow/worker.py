"""Worker process skeleton (M4 fills in the claim/run/ack loop)."""
from __future__ import annotations

import os
import socket
import time

from researchdesk import contracts as c
from researchdesk.metrics import events


def worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


def started_event(settings: c.Settings, wid: str) -> c.EventRecord:
    return c.EventRecord(
        ts_ms=int(time.time() * 1000), run_id=settings.run_id, client=c.Client.TEST.value,
        service="worker", event=c.EventName.WORKER_STARTED.value, worker_id=wid,
        fields={"pid": os.getpid()},
    )


def main() -> None:
    settings = c.Settings.from_env(os.environ)
    events.emit(settings, started_event(settings, worker_id()))
    while True:  # idle until M4 adds the claim loop
        time.sleep(60)


if __name__ == "__main__":
    main()
