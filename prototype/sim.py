"""Toy discrete-event simulation core (preliminary results only).

Time is simulated, so a "minute" of traffic runs in milliseconds. This is NOT the
real service: the real gateway/simulator live under src/researchdesk/.
"""
import hashlib
import heapq
import itertools
import re
from dataclasses import dataclass


def query_key(query: str) -> str:
    """Normalize a query so equivalent searches share one key.

    Lowercase, keep alphanumeric words, drop duplicates, sort. Deliberately lossy
    ("caching distributed" == "Distributed Caching!"); fine for a toy.
    """
    words = re.findall(r"[a-z0-9]+", query.lower())
    return " ".join(sorted(set(words)))


class Sim:
    """Minimal event loop driven by a simulated clock."""

    def __init__(self):
        self.now = 0.0
        self._events = []
        self._tiebreak = itertools.count()  # keeps same-time events in FIFO order

    def at(self, t, fn, *args):
        heapq.heappush(self._events, (t, next(self._tiebreak), fn, args))

    def after(self, delay, fn, *args):
        self.at(self.now + delay, fn, *args)

    def run(self, until=None):
        while self._events:
            t, _, fn, args = self._events[0]
            if until is not None and t > until:
                break
            heapq.heappop(self._events)
            self.now = t
            fn(*args)


@dataclass(frozen=True)
class Paper:
    id: int
    title: str


def make_corpus(n_papers: int = 200) -> list[Paper]:
    return [Paper(i, f"Synthetic paper {i}") for i in range(n_papers)]


def search(corpus: list[Paper], key: str, top: int = 5) -> tuple[int, ...]:
    """Deterministic ranked results: the same key always returns the same papers."""

    def score(paper: Paper) -> str:
        return hashlib.sha256(f"{key}|{paper.id}".encode()).hexdigest()

    return tuple(p.id for p in sorted(corpus, key=score)[:top])


class Backend:
    """arXiv-like provider.

    Limits: one call in flight, and call *starts* at least `pacing` seconds apart.
    The backend never refuses a call; it counts violations so a buggy gateway is
    caught instead of silently trusted.
    """

    def __init__(self, sim: Sim, corpus: list[Paper], pacing=3.0, latency=1.0):
        self.sim = sim
        self.corpus = corpus
        self.pacing = pacing
        self.latency = latency
        self.in_flight = 0
        self.last_start = None
        self.calls = 0
        self.overlap_violations = 0
        self.pacing_violations = 0

    def call(self, key: str, on_done) -> None:
        if self.in_flight >= 1:
            self.overlap_violations += 1
        if self.last_start is not None and self.sim.now - self.last_start < self.pacing - 1e-9:
            self.pacing_violations += 1
        self.in_flight += 1
        self.last_start = self.sim.now
        self.calls += 1
        self.sim.after(self.latency, self._finish, key, on_done)

    def _finish(self, key: str, on_done) -> None:
        self.in_flight -= 1
        on_done(search(self.corpus, key))
