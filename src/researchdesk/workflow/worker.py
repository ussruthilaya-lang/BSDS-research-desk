"""Worker process skeleton (M4 fills in the claim/run/ack loop)."""
from __future__ import annotations

import os
import socket
import threading
import time

from researchdesk import contracts as c
from researchdesk.metrics import events


def worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


def started_event(settings: c.Settings, wid: str, ts_ms: int = 0) -> c.EventRecord:
    return c.EventRecord(
        ts_ms=ts_ms, run_id=settings.run_id, client=c.Client.TEST.value,
        service="worker", event=c.EventName.WORKER_STARTED.value, worker_id=wid,
        fields={"pid": os.getpid()},
    )


def _resolve():
    """The real lease and runner functions when they exist, otherwise the stubs."""
    from researchdesk.workflow import stubs
    try:
        from researchdesk.workflow import lease
        claim, heartbeat, ack = lease.claim, lease.heartbeat, lease.ack
    except (ImportError, AttributeError):
        claim, heartbeat, ack = stubs.claim, stubs.heartbeat, stubs.ack
    try:
        from researchdesk.workflow import runner
        run = runner.run_subagent
    except (ImportError, AttributeError):
        run = stubs.run_subagent
    return claim, run, heartbeat, ack


def _event(settings, name: str, wid: str, task: dict | None = None, **fields) -> None:
    events.emit(settings, c.EventRecord(
        ts_ms=events.now_ms(settings), run_id=(task or {}).get("run_id", settings.run_id),
        client=(task or {}).get("client", c.Client.TEST.value), service="worker", event=name,
        trace_id=(task or {}).get("trace_id", ""), job_id=(task or {}).get("job_id", ""),
        subagent_id=int(task["subagent_id"]) if task else None, worker_id=wid,
        user=(task or {}).get("user", ""), fields=fields))


def process_one(settings: c.Settings, wid: str, claim, run, heartbeat, ack) -> bool:
    """Claim one task, run it with a heartbeat, ack it. False when no task was waiting.

    If `run` raises, the task is NOT acked, so a lease (RD_LEASES=on) can reclaim it.
    """
    got = claim(settings, wid)
    if got is None:
        return False
    entry_id, task = got
    _event(settings, c.EventName.TASK_CLAIMED.value, wid, task, attempt=int(task.get("attempt", 0)))
    stop = threading.Event()
    period = max(c.to_real_ms(settings.heartbeat_ms, settings.time_scale) / 1000, 0.01)

    def beat():
        while not stop.is_set():
            heartbeat(settings, wid, entry_id)
            _event(settings, c.EventName.WORKER_HEARTBEAT.value, wid, task)
            stop.wait(period)

    t = threading.Thread(target=beat, daemon=True)
    t.start()
    try:
        status = run(settings, task, wid)
    finally:
        stop.set()
        t.join()
    ack(settings, entry_id)
    events.count(settings, "rd_tasks_total", {"status": status})
    return True


def main() -> None:
    settings = c.Settings.from_env(os.environ)
    wid = worker_id()
    events.emit(settings, started_event(settings, wid, events.now_ms(settings)))
    claim, run, heartbeat, ack = _resolve()
    while True:
        if not process_one(settings, wid, claim, run, heartbeat, ack):
            time.sleep(0.2)


if __name__ == "__main__":
    main()
