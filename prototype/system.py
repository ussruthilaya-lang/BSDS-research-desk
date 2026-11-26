"""Workers, subagent tasks, gather and metrics for the toy simulation.

A job (or a one-subagent Question) is split into subagent tasks. Each worker slot runs one task at a
time: its searches in order, and after every result the agent "thinks" for `think_time` seconds
(reading results, refining the query). `think_time`, `plan_time` and `synth_time` are workload
assumptions, not measurements.

Job life, as in docs/contracts.md section 6:
  arrival -> the lead plans for `plan_time` -> N tasks join one queue -> free slots take them
  -> the gather stops waiting -> the lead writes the brief for `synth_time` -> final status.
Gather policies: `wait_all` waits for every subagent; `deadline_partial` also stops at the deadline
minus `margin` and keeps the subagents that have finished. A dropped search ends only its own
subagent. With one subagent, no plan time and no synth time, this reproduces the first prototype
exactly (tests/test_prototype_baseline.py and test_prototype_exp2.py guard that).

One difference from the contract text, to be settled in a contract change: section 6 makes a job
whose subagents all failed `failed`. Here, when every failure was the deadline (a task that never got
a slot, or a search the gateway dropped as too late) the job is `expired`, because the frozen
Experiment 1 baseline counts those as `expired`. `failed` means a non-deadline drop such as a full
queue.
"""
import math
from collections import deque
from dataclasses import dataclass, field

from gateway import Gateway
from reuse import ReuseLayer
from sim import Backend, Paper, Sim, make_corpus, query_key, search
from workload import Job, Question, make_jobs, make_workload, repeat_fraction_across, repeat_fraction_within

# Mirror the contract's RD_PLAN_MS, RD_SYNTH_MS and RD_GATHER_MARGIN_MS (tests/test_prototype_fanout.py
# checks it). The one-subagent baseline passes 0 for plan and synth so it matches the frozen results.
DEFAULT_PLAN_TIME = 2.0
DEFAULT_SYNTH_TIME = 4.0
DEFAULT_MARGIN = 5.0
GATHER_POLICIES = ("wait_all", "deadline_partial")


@dataclass(frozen=True)
class Outcome:
    qid: int
    status: str  # "on_time" | "late" | "expired" | "failed"  ("rejected" = refused at admission, not modelled yet)
    finish: float  # when the brief was written
    latency: float
    correct: bool
    completeness: float = 0.0  # subagents in the brief / subagents in the job
    n_subagents: int = 1
    used_calls: frozenset = frozenset()  # provider calls whose results are in this brief


def job_status(done: int, failure_reasons: list, brief_time: float, deadline: float) -> str:
    """Final job status. `done` is the number of finished subagents in the brief.

    With a brief: `on_time`, or `late` if it was written after the deadline. Without one: `failed` if
    any subagent was dropped for a reason other than the deadline, else `expired`. A reason of None
    means the subagent was still unfinished when the gather stopped.
    """
    if done:
        return "on_time" if brief_time <= deadline else "late"
    if any(reason not in (None, "expired") for reason in failure_reasons):
        return "failed"
    return "expired"


@dataclass
class _Task:
    job: "_Job"
    index: int
    queries: tuple
    status: str = "queued"  # queued | running | done | failed | expired
    reason: str | None = None
    results: list = field(default_factory=list)


@dataclass
class _Job:
    id: int
    arrival: float
    deadline: float  # absolute simulated time
    subagents: tuple
    tasks: list = field(default_factory=list)
    terminal: int = 0  # tasks that are done, failed or expired
    stopped: bool = False  # the gather has stopped waiting
    included: list = field(default_factory=list)
    failures: list = field(default_factory=list)


class System:
    def __init__(
        self,
        sim: Sim,
        gateway,
        corpus: list[Paper],
        n_workers: int,
        slots_per_worker: int = 1,
        think_time: float = 8.0,
        plan_time: float = 0.0,
        synth_time: float = 0.0,
        gather: str = "wait_all",
        margin: float = DEFAULT_MARGIN,
    ):
        if gather not in GATHER_POLICIES:
            raise ValueError(f"gather must be one of {GATHER_POLICIES}, got {gather!r}")
        if synth_time > margin:
            raise ValueError("synth_time must not exceed the gather margin (the brief has to fit inside it)")
        self.sim = sim
        self.gateway = gateway
        self.corpus = corpus
        self.think_time = think_time
        self.plan_time = plan_time
        self.synth_time = synth_time
        self.gather = gather
        self.margin = margin
        self.free_slots = n_workers * slots_per_worker
        self.pending: deque[_Task] = deque()  # subagent tasks waiting for a free worker slot
        self.max_pending = 0
        self.outcomes: list[Outcome] = []

    # -------------------------------------------------------------- arrival ----

    def load(self, items: list) -> None:
        """Schedule Jobs (N subagents) or Questions (one subagent) at their arrival times."""
        for item in items:
            self.sim.at(item.arrival, self._arrive, self._as_job(item))

    @staticmethod
    def _as_job(item) -> _Job:
        if isinstance(item, Question):
            return _Job(item.id, item.arrival, item.deadline, (item.queries,))
        return _Job(item.id, item.arrival, item.deadline, item.subagents)

    def _arrive(self, job: _Job) -> None:
        if self.gather == "deadline_partial":
            self.sim.at(max(self.sim.now, job.deadline - self.margin), self._stop_gather, job)
        if self.plan_time > 0:
            self.sim.after(self.plan_time, self._enqueue, job)
        else:
            self._enqueue(job)

    def _enqueue(self, job: _Job) -> None:
        if job.stopped:  # the gather already gave up while the lead was still planning
            return
        for index, queries in enumerate(job.subagents):
            task = _Task(job, index, queries)
            job.tasks.append(task)
            self.pending.append(task)
        self.max_pending = max(self.max_pending, len(self.pending))
        self._assign()

    # ------------------------------------------------------- running tasks -----

    def _assign(self) -> None:
        while self.free_slots and self.pending:
            task = self.pending.popleft()
            if self.sim.now >= task.job.deadline:  # waited too long for a worker slot
                self._end(task, "expired", "expired")
                continue
            task.status = "running"
            self.free_slots -= 1
            self._step(task, 0)

    def _step(self, task: _Task, i: int) -> None:
        if i == len(task.queries):
            self._finish_task(task)
            return
        self.gateway.submit(
            query_key(task.queries[i]),
            task.job.deadline,
            on_result=lambda res: self._got_result(task, i, res),
            on_drop=lambda reason: self._abort_task(task, reason),
        )

    def _got_result(self, task: _Task, i: int, result) -> None:
        task.results.append(result)
        self.sim.after(self.think_time, self._step, task, i + 1)

    def _finish_task(self, task: _Task) -> None:
        self._end(task, "done", None)
        self.free_slots += 1
        self._assign()

    def _abort_task(self, task: _Task, reason: str) -> None:
        self._end(task, "failed", reason)
        self.free_slots += 1
        # Scheduled, not called: a drop can fire inside gateway.submit, and a direct call would
        # recurse once per pending task during an overload.
        self.sim.after(0.0, self._assign)

    def _end(self, task: _Task, status: str, reason: str | None) -> None:
        task.status, task.reason = status, reason
        job = task.job
        job.terminal += 1
        if job.terminal == len(job.subagents):
            self._stop_gather(job)

    # ---------------------------------------------------------------- gather ---

    def _stop_gather(self, job: _Job) -> None:
        """Stop waiting: everyone is finished, or (deadline_partial) the margin timer fired."""
        if job.stopped:
            return
        job.stopped = True
        job.included = [t for t in job.tasks if t.status == "done"]
        # why each unfinished subagent is not in the brief; None means still queued or running at the stop
        job.failures = [t.reason if t.status in ("failed", "expired") else None for t in job.tasks if t.status != "done"]
        if self.synth_time > 0:
            self.sim.after(self.synth_time, self._finalize, job)
        else:
            self._finalize(job)

    def _finalize(self, job: _Job) -> None:
        """The brief is written: record the job's final outcome."""
        now = self.sim.now
        included = job.included
        status = job_status(len(included), job.failures, now, job.deadline)
        correct = bool(included) and all(
            list(t.results) == [search(self.corpus, query_key(q)) for q in t.queries] for t in included
        )
        used = frozenset(r.call_id for t in included for r in t.results if hasattr(r, "call_id"))
        self.outcomes.append(
            Outcome(job.id, status, now, now - job.arrival, correct, len(included) / len(job.subagents),
                    len(job.subagents), used)
        )


def p95(values: list[float]) -> float:
    """Nearest-rank 95th percentile; NaN for an empty list."""
    if not values:
        return math.nan
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def summarize(system: System, gateway: Gateway, backend: Backend, horizon: float, layer: ReuseLayer | None = None) -> dict:
    """Every contract section 12 column except run_id, setting and seed, plus the prototype's extras.

    `wasted_calls` is provider calls minus the distinct calls whose results are in an on-time correct
    brief (a call that served several steps counts once). It slightly overcounts at the window edge,
    where calls were made for jobs that were still running when the clock stopped.
    """
    outcomes = system.outcomes
    on_time = [o for o in outcomes if o.status == "on_time"]
    good = [o for o in on_time if o.correct]
    complete = [o for o in good if o.completeness == 1.0]
    used = set()
    for o in good:
        used |= o.used_calls
    count = lambda status: sum(o.status == status for o in outcomes)
    minutes = horizon / 60.0
    return {
        "briefs_per_min": len(good) / minutes,
        "complete_briefs_per_min": len(complete) / minutes,
        "on_time_correct": len(good),
        "wrong_briefs": sum(not o.correct for o in on_time),
        "late": count("late"),
        "expired": count("expired"),
        "rejected": count("rejected"),
        "failed": count("failed"),
        "upstream_calls": backend.calls,
        "calls_per_brief": backend.calls / len(good) if good else math.nan,
        "p95_latency_s": p95([o.latency for o in good]),
        "completeness_mean": sum(o.completeness for o in on_time) / len(on_time) if on_time else math.nan,
        "cache_hits": layer.hits if layer else 0,
        "merged": layer.merged if layer else 0,
        "wasted_calls": backend.calls - len(used),
        "max_queue_depth": gateway.max_depth,
        "max_pending": system.max_pending,
        "violations": backend.overlap_violations + backend.pacing_violations,
    }


def csv_row(result: dict, run_id: str, setting: str, seed: int) -> dict:
    """One row in the contract's harness CSV column order (docs/contracts.md section 12).

    Needs researchdesk importable (pip install -e . or PYTHONPATH=src); imported here so the other
    prototype scripts do not need it.
    """
    from researchdesk import contracts as c

    row = {"run_id": run_id, "setting": setting, "seed": seed}
    row.update({name: result[name] for name in c.HARNESS_CSV_COLUMNS if name not in row})
    return {name: row[name] for name in c.HARNESS_CSV_COLUMNS}


def _simulation(workers, slots_per_worker, think_time, max_queue, reuse_mode, ttl_s, latency=1.0, **system_kwargs):
    sim = Sim()
    corpus = make_corpus(200)
    backend = Backend(sim, corpus, latency=latency)
    gateway = Gateway(sim, backend, max_queue=max_queue)
    layer = ReuseLayer(sim, gateway, backend, mode=reuse_mode, ttl_s=ttl_s)
    system = System(sim, layer, corpus, workers, slots_per_worker, think_time, **system_kwargs)
    return sim, backend, gateway, layer, system


def run_baseline(
    workers: int,
    rate_per_min: float,
    k: int = 5,
    duration_s: float = 1800.0,
    seed: int = 0,
    think_time: float = 8.0,
    deadline_s: float = 120.0,
    pool_size: int = 5000,
    skew: float = 0.0,
    slots_per_worker: int = 1,
    max_queue: int = 50,
    n_questions: int | None = None,
    reuse_mode: str = "none",
    ttl_s: float = 600.0,
) -> dict:
    """One run of one-subagent jobs (no reuse unless `reuse_mode` says so). Counts only what finishes
    inside [0, duration_s].

    `n_questions` fixes the number of jobs (a burst); by default enough arrive to outlast the window.
    """
    sim, backend, gateway, layer, system = _simulation(
        workers, slots_per_worker, think_time, max_queue, reuse_mode, ttl_s
    )
    if n_questions is None:
        n_questions = int(rate_per_min * duration_s / 60.0 * 1.5) + 5  # enough to outlast the window
    system.load(
        make_workload(n_questions, rate_per_min, k, pool_size, skew, deadline_s=deadline_s, seed=seed)
    )
    sim.run(until=duration_s)
    return summarize(system, gateway, backend, duration_s, layer)


def run_jobs(
    workers: int,
    rate_per_min: float,
    n_subagents: int,
    k: int,
    cluster_size: int,
    pool_size: int,
    skew: float,
    duration_s: float = 1800.0,
    seed: int = 0,
    think_time: float = 8.0,
    deadline_s: float = 120.0,
    plan_time: float = DEFAULT_PLAN_TIME,
    synth_time: float = DEFAULT_SYNTH_TIME,
    gather: str = "deadline_partial",
    margin: float = DEFAULT_MARGIN,
    slots_per_worker: int = 1,
    max_queue: int = 50,
    n_jobs: int | None = None,
    reuse_mode: str = "none",
    ttl_s: float = 600.0,
    slowdown: float = 1.0,
) -> dict:
    """One run of deep-research jobs (N subagents of k searches each). `slowdown` multiplies the
    provider's latency (Experiment 3). Counts only what finishes inside [0, duration_s]."""
    sim, backend, gateway, layer, system = _simulation(
        workers, slots_per_worker, think_time, max_queue, reuse_mode, ttl_s, latency=1.0 * slowdown,
        plan_time=plan_time, synth_time=synth_time, gather=gather, margin=margin,
    )
    if n_jobs is None:
        n_jobs = int(rate_per_min * duration_s / 60.0 * 1.5) + 5  # enough to outlast the window
    jobs = make_jobs(n_jobs, rate_per_min, n_subagents, k, cluster_size, pool_size, skew, deadline_s, seed)
    system.load(jobs)
    sim.run(until=duration_s)
    result = summarize(system, gateway, backend, duration_s, layer)
    result["repeat_within"] = repeat_fraction_within(jobs)
    result["repeat_across"] = repeat_fraction_across(jobs)
    return result
