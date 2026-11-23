"""Event helper (contract section 9 and 11): `emit` and `count`, used by every service."""
from __future__ import annotations

import sys
from functools import lru_cache

import redis

from researchdesk import contracts as c


@lru_cache(maxsize=8)
def _client(url: str) -> redis.Redis:
    return redis.Redis.from_url(url, decode_responses=True)


def _redis(settings: c.Settings) -> redis.Redis:
    return _client(settings.redis_url)


def emit(settings: c.Settings, record: c.EventRecord) -> None:
    """Write one EventRecord as a JSON log line and as an entry in rd:events."""
    line = record.to_json()
    print(line, file=sys.stdout, flush=True)
    try:
        _redis(settings).xadd(
            c.EVENT_STREAM, {c.EVENT_FIELD: line},
            maxlen=c.EVENT_STREAM_MAXLEN, approximate=True,
        )
    except redis.RedisError as err:  # the log line above already holds the event
        print(f"events.emit: redis unavailable: {err}", file=sys.stderr, flush=True)


def metric_field(metric: str, labels: dict) -> str:
    """Hash field for one labelled counter, in Prometheus text form: name{a="x",b="y"}."""
    if metric not in c.METRICS:
        raise ValueError(f"unknown metric {metric!r}")
    expected = c.METRICS[metric][1]
    if set(labels) != set(expected):
        raise ValueError(f"{metric} takes labels {expected}, got {tuple(labels)}")
    if not labels:
        return metric
    body = ",".join(f'{k}="{labels[k]}"' for k in expected)
    return f"{metric}{{{body}}}"


def count(settings: c.Settings, metric: str, labels: dict, amount: int = 1) -> None:
    """Add `amount` to a counter in rd:metrics:{run_id}; the Job API exports that hash."""
    field = metric_field(metric, labels)
    try:
        _redis(settings).hincrby(c.metrics_key(settings.run_id), field, amount)
    except redis.RedisError as err:
        print(f"events.count: redis unavailable: {err}", file=sys.stderr, flush=True)
