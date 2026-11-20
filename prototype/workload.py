"""Seeded workload generator for the toy simulation.

A workload is a list of questions. Each question arrives at a random time
(Poisson process), carries a deadline, and runs a fixed script of `k` searches.
Query popularity follows a Zipf-like skew over a fixed pool: skew 0 is uniform
(mostly unique searches when the pool is large), higher skew concentrates traffic
on a few hot queries (highly repeated searches).
"""
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Question:
    id: int
    arrival: float  # seconds of simulated time
    deadline: float  # absolute simulated time by which the brief must be done
    queries: tuple[str, ...]  # the scripted searches, run in order


def make_query_pool(n: int) -> list[str]:
    return [f"topic {i}" for i in range(n)]


def zipf_weights(n: int, skew: float) -> list[float]:
    """Weight of rank i is 1 / (i + 1) ** skew. skew = 0 gives uniform weights."""
    return [1.0 / (i + 1) ** skew for i in range(n)]


def make_workload(
    n_questions: int,
    rate_per_min: float,
    k: int,
    pool_size: int,
    skew: float,
    deadline_s: float = 120.0,
    seed: int = 0,
) -> list[Question]:
    """Build a reproducible workload; the same arguments always give the same list."""
    if rate_per_min <= 0:
        raise ValueError("rate_per_min must be positive")
    if k < 1:
        raise ValueError("k must be at least 1")
    if pool_size < k:
        raise ValueError("pool_size must be at least k (a question never repeats a search)")
    if skew < 0:
        raise ValueError("skew must be non-negative")

    rng = random.Random(seed)
    pool = make_query_pool(pool_size)
    base_weights = zipf_weights(pool_size, skew)
    mean_gap = 60.0 / rate_per_min

    questions, t = [], 0.0
    for qid in range(n_questions):
        t += rng.expovariate(1.0 / mean_gap)
        weights = list(base_weights)
        chosen = []
        for _ in range(k):  # sample k distinct queries, weighted by popularity
            idx = rng.choices(range(pool_size), weights=weights)[0]
            chosen.append(pool[idx])
            weights[idx] = 0.0
        questions.append(Question(qid, t, t + deadline_s, tuple(chosen)))
    return questions
