"""Print one job's timeline from the events in rd:events.

    python -m researchdesk.metrics.timeline JOB_ID [--redis URL]
"""
from __future__ import annotations

import argparse
import json
import os

import redis

from researchdesk import contracts as c


def load(r: redis.Redis, trace_id: str) -> list[dict]:
    recs = [json.loads(f[c.EVENT_FIELD]) for _id, f in r.xrange(c.EVENT_STREAM)]
    return sorted((x for x in recs if x["trace_id"] == trace_id), key=lambda x: x["ts_ms"])


def render(recs: list[dict]) -> str:
    if not recs:
        return "no events for this trace_id"
    t0 = recs[0]["ts_ms"]
    lines = []
    for x in recs:
        who = f"sub {x['subagent_id']}" if x["subagent_id"] is not None else ""
        step = f" step {x['step']}" if x["step"] is not None else ""
        extra = " ".join(f"{k}={v}" for k, v in x["fields"].items())
        lines.append(f"+{x['ts_ms'] - t0:>8} ms  {x['service']:<8} {x['event']:<20} {who}{step} {extra}".rstrip())
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("trace_id")
    p.add_argument("--redis", default=os.environ.get("RD_REDIS_URL", "redis://localhost:6379/0"))
    a = p.parse_args()
    print(render(load(redis.Redis.from_url(a.redis, decode_responses=True), a.trace_id)))


if __name__ == "__main__":
    main()
