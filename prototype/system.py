"""Workers, question outcomes, and metrics for the baseline (no-reuse) system.

Each worker slot runs one question at a time. A question is a script of searches
run in order; after every result the agent "thinks" for `think_time` seconds
(reading results, refining the query, assembling the brief) before the next step.
`think_time` is a workload assumption, not a measurement.
"""
import math
from collections import deque
from dataclasses import dataclass

from gateway import Gateway
from sim import Backend, Paper, Sim, make_corpus, query_key, search
from workload import Question, make_workload


@dataclass(frozen=True)
class Outcome:
    qid: int
    status: str  # "on_time" | "late" | "expired" | "rejected"
    finish: float
    latency: float
    correct: bool


class System:
    def __init__(
        self,
        sim: Sim,
        gateway: Gateway,
        corpus: list[Paper],
        n_workers: int,
        slots_per_worker: int = 1,
        think_time: float = 8.0,
    ):
        self.sim = sim
        self.gateway = gateway
        self.corpus = corpus
        self.think_time = think_time
        self.free_slots = n_workers * slots_per_worker
        self.pending: deque[Question] = deque()
        self.outcomes: list[Outcome] = []

    def load(self, questions: list[Question]) -> None:
        for q in questions:
            self.sim.at(q.arrival, self._arrive, q)

    def _arrive(self, q: Question) -> None:
        self.pending.append(q)
        self._assign()

    def _assign(self) -> None:
        while self.free_slots and self.pending:
            q = self.pending.popleft()
            if self.sim.now >= q.deadline:  # waited too long for a worker
                self._record(q, "expired", correct=False)
                continue
            self.free_slots -= 1
            self._step(q, 0, [])

    def _step(self, q: Question, i: int, results: list) -> None:
        if i == len(q.queries):
            self._finish(q, results)
            return
        key = query_key(q.queries[i])
        self.gateway.submit(
            key,
            q.deadline,
            on_result=lambda res: self.sim.after(self.think_time, self._step, q, i + 1, results + [res]),
            on_drop=lambda reason: self._abort(q, reason),
        )

    def _finish(self, q: Question, results: list) -> None:
        expected = [search(self.corpus, query_key(text)) for text in q.queries]
        status = "on_time" if self.sim.now <= q.deadline else "late"
        self._record(q, status, correct=list(results) == expected)
        self.free_slots += 1
        self._assign()

    def _abort(self, q: Question, reason: str) -> None:
        self._record(q, reason, correct=False)
        self.free_slots += 1
        # Scheduled, not called: abort can fire inside gateway.submit, and a direct call
        # would recurse once per pending question during an overload.
        self.sim.after(0.0, self._assign)

    def _record(self, q: Question, status: str, correct: bool) -> None:
        self.outcomes.append(Outcome(q.id, status, self.sim.now, self.sim.now - q.arrival, correct))


def p95(values: list[float]) -> float:
    """Nearest-rank 95th percentile; NaN for an empty list."""
    if not values:
        return math.nan
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def summarize(system: System, gateway: Gateway, backend: Backend, horizon: float) -> dict:
    good = [o for o in system.outcomes if o.status == "on_time" and o.correct]
    count = lambda status: sum(o.status == status for o in system.outcomes)
    return {
        "briefs_per_min": len(good) / (horizon / 60.0),
        "on_time_correct": len(good),
        "wrong_briefs": sum(o.status == "on_time" and not o.correct for o in system.outcomes),
        "late": count("late"),
        "expired": count("expired"),
        "rejected": count("rejected"),
        "upstream_calls": backend.calls,
        "calls_per_brief": backend.calls / len(good) if good else math.nan,
        "p95_latency_s": p95([o.latency for o in good]),
        "max_queue_depth": gateway.max_depth,
        "violations": backend.overlap_violations + backend.pacing_violations,
    }


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
) -> dict:
    """One no-reuse run. Counts only what finishes inside [0, duration_s]."""
    sim = Sim()
    corpus = make_corpus(200)
    backend = Backend(sim, corpus)
    gateway = Gateway(sim, backend, max_queue=max_queue)
    system = System(sim, gateway, corpus, workers, slots_per_worker, think_time)
    n_questions = int(rate_per_min * duration_s / 60.0 * 1.5) + 5  # enough to outlast the window
    system.load(
        make_workload(n_questions, rate_per_min, k, pool_size, skew, deadline_s=deadline_s, seed=seed)
    )
    sim.run(until=duration_s)
    return summarize(system, gateway, backend, duration_s)
