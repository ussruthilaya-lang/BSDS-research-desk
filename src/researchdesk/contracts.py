"""Shared contract for every Research Desk service (contract version 1).

docs/contracts.md explains every name in this file, and tests/test_contracts.py
keeps the two in sync. Change both in one PR that all three owners approve.
Standard library only, so every service (and the prototype) can import it.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from typing import Any, Mapping

CONTRACT_VERSION = "1"

# ---------------------------------------------------------------- time ------
# A name ending in _ms is a SIMULATED duration or deadline. A name ending in _at_ms, and ts_ms,
# is an absolute REAL time on the shared clock (Redis TIME). Multiply a simulated duration by
# RD_TIME_SCALE only to sleep or wait. See docs/contracts.md section 2.


def to_real_ms(sim_ms: float, time_scale: float) -> float:
    """Simulated ms -> real ms (what to sleep or wait)."""
    return sim_ms * time_scale


def to_sim_ms(real_ms: float, time_scale: float) -> float:
    """Real ms measured on a clock -> simulated ms."""
    return real_ms / time_scale


def redis_time_to_ms(reply) -> int:
    """Redis TIME replies [unix seconds, microseconds]. This is the shared clock, in real ms."""
    seconds, micros = (int(x) for x in reply)
    return seconds * 1000 + micros // 1000


# ------------------------------------------------------- query identity -----


def query_key(query: str) -> str:
    """Same rule as prototype/sim.py: lowercase, alphanumeric words, no duplicates, sorted."""
    return " ".join(sorted(set(re.findall(r"[a-z0-9]+", query.lower()))))


# ---------------------------------------------------------------- enums -----


class Client(str, Enum):
    HARNESS = "harness"  # scripted replays: the only source of measured results
    CLAUDE = "claude"  # calls made through the MCP server: demo only, never measured
    TEST = "test"  # unit and integration tests


class DropReason(str, Enum):
    QUEUE_FULL = "queue_full"
    DEADLINE_UNMEETABLE = "deadline_unmeetable"
    RETRY_BUDGET_EXHAUSTED = "retry_budget_exhausted"
    ADMISSION_REJECTED = "admission_rejected"
    PROVIDER_ERROR = "provider_error"
    USER_QUOTA = "user_quota"  # the user is over RD_USER_CALLS_PER_MIN or RD_USER_QUEUE_MAX


class JobStatus(str, Enum):
    ADMITTED = "admitted"
    RUNNING = "running"
    ON_TIME = "on_time"
    LATE = "late"
    EXPIRED = "expired"
    REJECTED = "rejected"
    FAILED = "failed"


FINAL_JOB_STATUSES = frozenset(
    {JobStatus.ON_TIME, JobStatus.LATE, JobStatus.EXPIRED, JobStatus.REJECTED, JobStatus.FAILED}
)


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class SearchSource(str, Enum):
    CACHE = "cache"
    MERGED = "merged"
    PROVIDER = "provider"


class ReuseMode(str, Enum):
    NONE = "none"
    CACHE = "cache"
    CACHE_MERGE = "cache_merge"


class GatherPolicy(str, Enum):
    WAIT_ALL = "wait_all"
    DEADLINE_PARTIAL = "deadline_partial"


class QueuePolicy(str, Enum):
    FIFO = "fifo"
    ROUND_ROBIN = "round_robin"  # one request per job in turn
    FAIR_USER = "fair_user"  # one request per user in turn (the public service)


class EventName(str, Enum):
    RUN_STARTED = "run.started"
    RUN_FINISHED = "run.finished"
    JOB_SUBMITTED = "job.submitted"
    JOB_ADMITTED = "job.admitted"
    JOB_REJECTED = "job.rejected"
    JOB_PLANNED = "job.planned"
    JOB_GATHERED = "job.gathered"
    JOB_FINISHED = "job.finished"
    TASK_ENQUEUED = "task.enqueued"
    TASK_CLAIMED = "task.claimed"
    TASK_STEP_DONE = "task.step_done"
    TASK_LEASE_EXPIRED = "task.lease_expired"
    TASK_RECLAIMED = "task.reclaimed"
    TASK_DONE = "task.done"
    TASK_FAILED = "task.failed"
    SEARCH_CACHE_HIT = "search.cache_hit"
    SEARCH_MERGED = "search.merged"
    SEARCH_CLAIMED = "search.claimed"
    SEARCH_STALE = "search.stale"
    SEARCH_DONE = "search.done"
    GATEWAY_QUEUED = "gateway.queued"
    GATEWAY_SENT = "gateway.sent"
    GATEWAY_DROPPED = "gateway.dropped"
    GATEWAY_RETRY = "gateway.retry"
    GATEWAY_ADMISSION = "gateway.admission"
    PROVIDER_SERVED = "provider.served"
    PROVIDER_VIOLATION = "provider.violation"
    PROVIDER_FAULT = "provider.fault"
    WORKER_STARTED = "worker.started"
    WORKER_HEARTBEAT = "worker.heartbeat"


# ---------------------------------------------------- services and HTTP -----

PORTS = {"api": 8000, "provider": 8001, "gateway": 8002, "mcp": 8003, "board": 8004}

ENDPOINTS = {
    "api": ("POST /jobs", "GET /jobs/{job_id}", "GET /jobs/{job_id}/trace", "POST /search", "GET /health", "GET /metrics"),
    "gateway": ("POST /dispatch", "POST /admit", "GET /health", "GET /metrics"),
    "provider": ("POST /search", "GET /stats", "POST /faults", "POST /reset", "GET /health", "GET /metrics"),
    "mcp": ("POST /mcp", "POST /mcp/u/{user}"),
    "board": ("GET /", "GET /events/stream", "GET /health"),
}

# Cross-lane Python functions: module -> function names (signatures in docs/contracts.md §8).
IN_PROCESS_INTERFACES = {
    "researchdesk.workflow.runner": ("search_once", "run_subagent", "resume_step"),
    "researchdesk.workflow.lead": ("plan", "gather"),
    "researchdesk.workflow.lease": ("claim", "heartbeat", "ack"),
    "researchdesk.metrics.events": ("emit", "count"),
}

HTTP_STATUS = {
    "ok": 200,
    "accepted": 202,
    "bad_request": 400,
    "not_found": 404,
    "conflict": 409,
    "quota": 429,
    "provider_fault": 500,
    "dropped": 503,
}

USER_PATTERN = r"[a-z0-9-]{1,32}"  # the {user} handle in /mcp/u/{user}; "anon" when absent


def valid_user(name: str) -> bool:
    return re.fullmatch(USER_PATTERN, name) is not None

MCP_TRANSPORTS = ("stdio", "streamable-http")  # stdio: Claude Desktop chat; HTTP: Claude Code and Compose
MCP_UI_RESOURCE = "ui://researchdesk/progress.html"  # optional MCP App progress card (task T12b)

MCP_TOOLS = {
    "start_research": ("question", "deadline_s", "plan"),
    "get_research": ("job_id",),
    "search_papers": ("query", "deadline_s"),
}

# ----------------------------------------------------------- redis keys -----

TASK_STREAM = "rd:tasks"
TASK_GROUP = "workers"
EVENT_STREAM = "rd:events"
EVENT_STREAM_MAXLEN = 100_000
EVENT_FIELD = "data"
CORPUS_VERSION_KEY = "rd:corpus_version"  # latest version the gateway has seen from the provider


def metrics_key(run_id: str) -> str:
    """Hash of worker-side counters; the Job API exports it on GET /metrics."""
    return f"rd:metrics:{run_id}"


def cache_key(qkey: str) -> str:
    return f"rd:cache:{qkey}"


def inflight_key(qkey: str) -> str:
    return f"rd:inflight:{qkey}"


def waiters_key(qkey: str) -> str:
    return f"rd:waiters:{qkey}"


def done_channel(qkey: str) -> str:
    return f"rd:done:{qkey}"


def job_key(job_id: str) -> str:
    return f"rd:job:{job_id}"


def subagent_key(job_id: str, subagent_id: int) -> str:
    return f"rd:job:{job_id}:sub:{subagent_id}"


def checkpoint_key(job_id: str, subagent_id: int, step: int) -> str:
    return f"rd:ckpt:{job_id}:{subagent_id}:{step}"


def heartbeat_key(worker_id: str) -> str:
    return f"rd:hb:{worker_id}"


# -------------------------------------------------------------- metrics -----
# name -> (Prometheus type, labels). Every metric also carries the run_id label.

METRICS = {
    "rd_jobs_total": ("counter", ("status",)),
    "rd_tasks_total": ("counter", ("status",)),
    "rd_searches_total": ("counter", ("source",)),
    "rd_merge_waiters_total": ("counter", ()),
    "rd_stale_answers_total": ("counter", ()),
    "rd_gateway_queue_depth": ("gauge", ()),
    "rd_gateway_calls_total": ("counter", ()),
    "rd_gateway_drops_total": ("counter", ("reason",)),
    "rd_gateway_retries_total": ("counter", ()),
    "rd_admission_total": ("counter", ("decision",)),
    "rd_provider_calls_total": ("counter", ()),
    "rd_provider_violations_total": ("counter", ("kind",)),
    "rd_lease_expiries_total": ("counter", ()),
}

HARNESS_CSV_COLUMNS = (
    "run_id", "setting", "seed", "briefs_per_min", "on_time_correct", "wrong_briefs", "late",
    "expired", "rejected", "failed", "upstream_calls", "calls_per_brief", "p95_latency_s",
    "completeness_mean", "cache_hits", "merged", "wasted_calls", "max_queue_depth", "violations",
)

# ------------------------------------------------------ wire messages -------


def _decode(cls, data: Mapping[str, Any]):
    """Build a dataclass from a dict. Unknown keys and missing required keys raise ValueError."""
    if not isinstance(data, Mapping):
        raise ValueError(f"{cls.__name__}: expected an object")
    names = {f.name for f in fields(cls)}
    unknown = set(data) - names
    if unknown:
        raise ValueError(f"{cls.__name__}: unknown fields {sorted(unknown)}")
    nested = getattr(cls, "_nested", {})
    kwargs = {}
    for k, v in data.items():
        if k in nested and v is not None:
            v = [_decode(nested[k], item) for item in v]
        kwargs[k] = v
    try:
        return cls(**kwargs)
    except TypeError as exc:  # a required field is missing
        raise ValueError(f"{cls.__name__}: {exc}") from None


class _Wire:
    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]):
        return _decode(cls, data)

    @classmethod
    def from_json(cls, text: str):
        return cls.from_dict(json.loads(text))


@dataclass
class SubagentPlan(_Wire):
    subagent_id: int
    queries: list[str]


@dataclass
class JobRequest(_Wire):  # POST /jobs (api)
    question: str
    deadline_ms: int  # remaining simulated ms when the request is sent
    client: str
    run_id: str
    plan: list[SubagentPlan] | None = None  # None: the lead builds the plan
    job_id: str | None = None  # the harness passes the workload's id
    gather: str | None = None  # GatherPolicy value; None: RD_GATHER_POLICY
    user: str = "anon"  # handle from /mcp/u/{user}; quotas apply per user
    _nested = {"plan": SubagentPlan}


@dataclass
class JobAccepted(_Wire):  # 202 reply to POST /jobs
    job_id: str
    trace_id: str
    status: str  # "admitted" or "rejected"


@dataclass
class SubagentView(_Wire):
    subagent_id: int
    status: str  # TaskStatus value
    steps_done: int
    k: int
    paper_ids: list[list[int]]  # one list per finished step
    stale_steps: int = 0  # steps answered from a cache entry older than the latest corpus version


@dataclass
class JobView(_Wire):  # GET /jobs/{job_id}
    job_id: str
    status: str  # JobStatus value
    completeness: float  # finished subagents / n_subagents in the brief
    n_subagents: int
    subagents: list[SubagentView]
    created_at_ms: int
    finished_at_ms: int | None = None
    _nested = {"subagents": SubagentView}


@dataclass
class SearchRequest(_Wire):  # POST /search (api): one search, used by Mode B
    query: str
    deadline_ms: int
    client: str
    run_id: str
    user: str = "anon"


@dataclass
class SearchResult(_Wire):
    status: str  # "ok" or "dropped"
    key: str
    paper_ids: list[int]
    latency_ms: float
    source: str | None = None  # SearchSource value when ok
    corpus_version: int | None = None
    reason: str | None = None  # DropReason value when dropped


@dataclass
class DispatchRequest(_Wire):  # POST /dispatch (gateway)
    key: str
    deadline_ms: int
    client: str
    run_id: str
    trace_id: str
    attempt: int = 0
    job_id: str | None = None
    subagent_id: int | None = None
    user: str = "anon"


@dataclass
class DispatchResult(_Wire):
    status: str  # "ok" or "dropped"
    key: str
    paper_ids: list[int]
    queue_wait_ms: float
    provider_ms: float
    corpus_version: int | None = None
    reason: str | None = None


@dataclass
class AdmitRequest(_Wire):  # POST /admit (gateway)
    job_id: str
    n_subagents: int
    k: int
    deadline_ms: int
    expected_hit_rate: float = 0.0
    user: str = "anon"


@dataclass
class AdmitResult(_Wire):
    admitted: bool
    estimated_ms: int
    reason: str | None = None


@dataclass
class ProviderSearchRequest(_Wire):  # POST /search (provider)
    key: str
    request_id: str
    client: str
    run_id: str
    trace_id: str


@dataclass
class ProviderSearchResult(_Wire):
    key: str
    paper_ids: list[int]
    corpus_version: int
    started_at_ms: int
    finished_at_ms: int


@dataclass
class FaultPlan(_Wire):  # POST /faults (provider)
    slowdown: float = 1.0
    error_rate: float = 0.0
    pause_windows_ms: list[list[int]] = field(default_factory=list)


@dataclass
class ProviderStats(_Wire):  # GET /stats?run_id=... (provider)
    run_id: str
    calls: int
    overlap_violations: int
    pacing_violations: int
    corpus_version: int


@dataclass
class WorkloadJob(_Wire):
    job_id: str
    arrival_s: float  # simulated seconds from the start of the run
    deadline_s: float  # simulated seconds AFTER arrival (relative, not absolute)
    plan: list[SubagentPlan]
    _nested = {"plan": SubagentPlan}


@dataclass
class WorkloadFile(_Wire):  # written by prototype/workload.py, replayed by harness/
    version: int
    seed: int
    params: dict
    jobs: list[WorkloadJob]
    _nested = {"jobs": WorkloadJob}


@dataclass
class EventRecord(_Wire):  # one line in the logs and one entry in rd:events
    ts_ms: int  # shared clock (Redis TIME), real ms
    run_id: str
    client: str
    service: str
    event: str  # EventName value
    trace_id: str = ""
    job_id: str = ""
    subagent_id: int | None = None
    step: int | None = None
    worker_id: str = ""
    key: str = ""
    fields: dict = field(default_factory=dict)
    user: str = ""

    def __post_init__(self):
        if self.event not in {e.value for e in EventName}:
            raise ValueError(f"unknown event {self.event!r}")
        if self.client not in {c.value for c in Client}:
            raise ValueError(f"unknown client {self.client!r}")


# ------------------------------------------------------------- settings -----

_ENUM_SETTINGS = {
    "queue_policy": QueuePolicy,
    "reuse_mode": ReuseMode,
    "gather_policy": GatherPolicy,
}

ENV_VARS = {
    "time_scale": "RD_TIME_SCALE",
    "pacing_ms": "RD_PACING_MS",
    "pacing_safety_real_ms": "RD_PACING_SAFETY_REAL_MS",
    "provider_latency_ms": "RD_PROVIDER_LATENCY_MS",
    "provider_latency_jitter": "RD_PROVIDER_LATENCY_JITTER",
    "corpus_size": "RD_CORPUS_SIZE",
    "corpus_version_every_ms": "RD_CORPUS_VERSION_EVERY_MS",
    "queue_max": "RD_QUEUE_MAX",
    "queue_policy": "RD_QUEUE_POLICY",
    "admission": "RD_ADMISSION",
    "retry_budget": "RD_RETRY_BUDGET",
    "user_calls_per_min": "RD_USER_CALLS_PER_MIN",
    "user_queue_max": "RD_USER_QUEUE_MAX",
    "leases": "RD_LEASES",
    "lease_ms": "RD_LEASE_MS",
    "heartbeat_ms": "RD_HEARTBEAT_MS",
    "inflight_lease_ms": "RD_INFLIGHT_LEASE_MS",
    "cache_ttl_ms": "RD_CACHE_TTL_MS",
    "reuse_mode": "RD_REUSE_MODE",
    "gather_policy": "RD_GATHER_POLICY",
    "gather_margin_ms": "RD_GATHER_MARGIN_MS",
    "think_ms": "RD_THINK_MS",
    "seed": "RD_SEED",
    "run_id": "RD_RUN_ID",
    "redis_url": "RD_REDIS_URL",
    "provider_url": "RD_PROVIDER_URL",
    "gateway_url": "RD_GATEWAY_URL",
    "api_url": "RD_API_URL",
    "public_host": "RD_PUBLIC_HOST",
}


@dataclass(frozen=True)
class Settings:
    time_scale: float = 1.0
    pacing_ms: int = 3000
    pacing_safety_real_ms: int = 5  # the one REAL-ms setting: gateway's margin over the pacing gap
    provider_latency_ms: int = 1000
    provider_latency_jitter: float = 0.0  # 0 = fixed latency, as in the prototype
    corpus_size: int = 200
    corpus_version_every_ms: int = 0  # 0 = the corpus never changes
    queue_max: int = 50
    queue_policy: str = QueuePolicy.FIFO.value
    admission: bool = True
    retry_budget: int = 2
    user_calls_per_min: int = 0  # per-user cap on provider calls a minute; 0 = no cap (experiments)
    user_queue_max: int = 0  # per-user cap on queued requests; 0 = no cap
    leases: bool = True  # off: a crashed worker's task is never reclaimed (E4 baseline)
    lease_ms: int = 10_000
    heartbeat_ms: int = 3_000
    inflight_lease_ms: int = 15_000
    cache_ttl_ms: int = 600_000
    reuse_mode: str = ReuseMode.CACHE_MERGE.value
    gather_policy: str = GatherPolicy.DEADLINE_PARTIAL.value
    gather_margin_ms: int = 5_000
    think_ms: int = 8_000
    seed: int = 0
    run_id: str = "dev"
    redis_url: str = "redis://redis:6379/0"
    provider_url: str = "http://provider:8001"
    gateway_url: str = "http://gateway:8002"
    api_url: str = "http://api:8000"
    public_host: str = ""  # tunnel hostname the MCP server accepts besides localhost

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        kwargs: dict[str, Any] = {}
        for f in fields(cls):
            raw = env.get(ENV_VARS[f.name])
            if raw is None:
                continue
            if f.type in ("bool", bool):
                if raw.lower() not in ("on", "off", "true", "false", "1", "0"):
                    raise ValueError(f"{ENV_VARS[f.name]}: expected on/off, got {raw!r}")
                kwargs[f.name] = raw.lower() in ("on", "true", "1")
            elif f.type in ("int", int):
                kwargs[f.name] = int(raw)
            elif f.type in ("float", float):
                kwargs[f.name] = float(raw)
            else:
                kwargs[f.name] = raw
        settings = cls(**kwargs)
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.time_scale <= 0:
            raise ValueError("RD_TIME_SCALE must be positive")
        for name, enum in _ENUM_SETTINGS.items():
            value = getattr(self, name)
            if value not in {e.value for e in enum}:
                raise ValueError(f"{ENV_VARS[name]}: {value!r} is not one of {[e.value for e in enum]}")
