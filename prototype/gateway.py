"""Baseline gateway for the toy simulation: FIFO, bounded, paced, deadline-aware.

No cache and no merging yet (stage 3). Every submitted search becomes one upstream
call unless it is rejected (queue full) or dropped (deadline cannot be met).
"""
from collections import deque
from dataclasses import dataclass

from sim import Backend, Sim


@dataclass
class _Request:
    key: str
    deadline: float
    on_result: object  # callable(result)
    on_drop: object  # callable(reason) with reason in {"rejected", "expired"}


class Gateway:
    def __init__(self, sim: Sim, backend: Backend, max_queue: int = 50):
        self.sim = sim
        self.backend = backend
        self.max_queue = max_queue
        self.queue: deque[_Request] = deque()
        self.in_flight = False
        self.next_allowed = 0.0  # earliest simulated time the next call may start
        self._wake_pending = False
        self.rejected = 0
        self.expired = 0
        self.max_depth = 0

    def submit(self, key: str, deadline: float, on_result, on_drop) -> None:
        """Queue a search. Rejects immediately if the bounded queue is full."""
        if len(self.queue) >= self.max_queue:
            self.rejected += 1
            on_drop("rejected")
            return
        self.queue.append(_Request(key, deadline, on_result, on_drop))
        self.max_depth = max(self.max_depth, len(self.queue))
        self._pump()

    def _pump(self) -> None:
        """Dispatch from the queue head whenever the pacer and concurrency allow."""
        while self.queue and not self.in_flight:
            if self.sim.now < self.next_allowed:
                if not self._wake_pending:
                    self._wake_pending = True
                    self.sim.at(self.next_allowed, self._wake)
                return
            req = self.queue.popleft()
            # Deadline check before dispatch: a result that would arrive late is
            # useless, so do not spend an upstream call on it (and no pacing slot).
            if self.sim.now + self.backend.latency > req.deadline:
                self.expired += 1
                req.on_drop("expired")
                continue
            self.in_flight = True
            self.next_allowed = self.sim.now + self.backend.pacing
            self.backend.call(req.key, lambda result, r=req: self._done(r, result))

    def _wake(self) -> None:
        self._wake_pending = False
        self._pump()

    def _done(self, req: _Request, result) -> None:
        self.in_flight = False
        req.on_result(result)
        self._pump()
