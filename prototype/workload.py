"""Seeded workload generator for the toy simulation.

A workload is a list of questions. Each question arrives at a random time
(Poisson process), carries a deadline, and runs a fixed script of `k` searches.
Query popularity follows a Zipf-like skew over a fixed pool: skew 0 is uniform
(mostly unique searches when the pool is large), higher skew concentrates traffic
on a few hot queries (highly repeated searches).
"""
import random
import re
from dataclasses import dataclass

from sim import query_key


@dataclass(frozen=True)
class Question:
    id: int
    arrival: float  # seconds of simulated time
    deadline: float  # absolute simulated time by which the brief must be done
    queries: tuple[str, ...]  # the scripted searches, run in order


def repeat_fraction(questions: list[Question]) -> float:
    """Share of all searches whose key already appeared earlier in arrival order.

    This is the ceiling on what reuse can save: ~0 means mostly unique searches,
    values near 1 mean highly repeated searches. Use it to label workloads.
    """
    seen, repeats, total = set(), 0, 0
    for q in sorted(questions, key=lambda q: q.arrival):
        for query in q.queries:
            key = query_key(query)
            repeats += key in seen
            seen.add(key)
            total += 1
    return repeats / total if total else 0.0


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


# ------------------------------------------------ deep-research jobs (S2) ----
# A job has N subagents. Each job draws ONE topic cluster of c distinct queries from the pool, with
# the Zipf popularity weights, and each subagent picks k distinct queries uniformly from that
# cluster (c >= k). A small cluster means the subagents of one job repeat each other's searches
# (within-job overlap); a hot pool means different jobs repeat each other (across-job overlap).
# make_workload above is the one-subagent case and is unchanged.


@dataclass(frozen=True)
class Job:
    id: int
    arrival: float  # seconds of simulated time
    deadline_s: float  # seconds AFTER arrival; kept relative so the JSON round-trips exactly
    subagents: tuple[tuple[str, ...], ...]  # per subagent, its k searches in order

    @property
    def deadline(self) -> float:
        """Absolute simulated time, like Question.deadline."""
        return self.arrival + self.deadline_s


class JobList(list):
    """A list of Job that remembers how it was made, so to_json can record it in the file."""

    params: dict
    seed: int


def make_jobs(
    n_jobs: int,
    rate_per_min: float,
    n_subagents: int,
    k: int,
    cluster_size: int,
    pool_size: int,
    skew: float,
    deadline_s: float = 120.0,
    seed: int = 0,
) -> JobList:
    """Build reproducible deep-research jobs; the same arguments always give the same list."""
    if n_jobs < 0:
        raise ValueError("n_jobs must not be negative")
    if rate_per_min <= 0:
        raise ValueError("rate_per_min must be positive")
    if n_subagents < 1:
        raise ValueError("n_subagents must be at least 1")
    if k < 1:
        raise ValueError("k must be at least 1")
    if cluster_size < k:
        raise ValueError("cluster_size must be at least k (a subagent never repeats a search)")
    if pool_size < cluster_size:
        raise ValueError("pool_size must be at least cluster_size")
    if skew < 0:
        raise ValueError("skew must be non-negative")
    if deadline_s <= 0:
        raise ValueError("deadline_s must be positive")

    rng = random.Random(seed)
    pool = make_query_pool(pool_size)
    base_weights = zipf_weights(pool_size, skew)
    mean_gap = 60.0 / rate_per_min

    jobs = JobList()
    t = 0.0
    for job_id in range(n_jobs):
        t += rng.expovariate(1.0 / mean_gap)
        weights = list(base_weights)
        cluster = []
        for _ in range(cluster_size):  # the topic cluster: distinct queries, weighted by popularity
            idx = rng.choices(range(pool_size), weights=weights)[0]
            cluster.append(pool[idx])
            weights[idx] = 0.0
        subagents = tuple(tuple(rng.sample(cluster, k)) for _ in range(n_subagents))
        jobs.append(Job(job_id, t, deadline_s, subagents))
    jobs.seed = seed
    jobs.params = dict(
        n_jobs=n_jobs, rate_per_min=rate_per_min, n_subagents=n_subagents, k=k, cluster_size=cluster_size,
        pool_size=pool_size, skew=skew, deadline_s=deadline_s,
    )
    return jobs


def _repeat_counts(jobs) -> tuple[int, int, int]:
    """(within-job repeats, across-job repeats, total searches).

    A search is a within-job repeat if its key already appeared earlier in the same job, else an
    across-job repeat if it appeared in an earlier job (by arrival), else new. Counts do not depend
    on the order of the searches inside a job.
    """
    seen_before, within, across, total = set(), 0, 0, 0
    for job in sorted(jobs, key=lambda j: j.arrival):
        in_job = set()
        for sub in job.subagents:
            for query in sub:
                key = query_key(query)
                total += 1
                if key in in_job:
                    within += 1
                elif key in seen_before:
                    across += 1
                in_job.add(key)
        seen_before |= in_job
    return within, across, total


def repeat_fraction_within(jobs) -> float:
    """Share of all searches that repeat one already asked by an earlier subagent of the same job."""
    within, _, total = _repeat_counts(jobs)
    return within / total if total else 0.0


def repeat_fraction_across(jobs) -> float:
    """Share of all searches that are new to their job but already asked in an earlier job.

    within + across is the overall share of searches whose key was seen before (the ceiling on what
    reuse can save); the split says which kind of overlap it is.
    """
    _, across, total = _repeat_counts(jobs)
    return across / total if total else 0.0


def to_json(jobs, seed: int | None = None, params: dict | None = None) -> str:
    """Serialize jobs as a contract WorkloadFile (docs/contracts.md section 12).

    `params` adds to what make_jobs recorded; set "duration_s" to give the replay harness its
    measurement window (it falls back to the end of the last job). Needs researchdesk importable
    (pip install -e . or PYTHONPATH=src); imported here so the other prototype scripts do not.
    """
    from researchdesk import contracts as c

    recorded = dict(getattr(jobs, "params", {}))
    recorded.update(params or {})
    file_seed = seed if seed is not None else getattr(jobs, "seed", 0)
    workload = c.WorkloadFile(
        version=1,
        seed=file_seed,
        params=recorded,
        jobs=[
            c.WorkloadJob(
                job_id=f"j{job.id}",
                arrival_s=job.arrival,
                deadline_s=job.deadline_s,
                plan=[c.SubagentPlan(i, list(sub)) for i, sub in enumerate(job.subagents)],
            )
            for job in jobs
        ],
    )
    return workload.to_json()


def from_json(text: str) -> JobList:
    """Read a contract WorkloadFile back into jobs (the inverse of to_json)."""
    from researchdesk import contracts as c

    workload = c.WorkloadFile.from_json(text)
    jobs = JobList()
    for index, wj in enumerate(workload.jobs):
        match = re.fullmatch(r"j(\d+)", wj.job_id)
        jobs.append(
            Job(
                int(match.group(1)) if match else index,
                wj.arrival_s,
                wj.deadline_s,
                tuple(tuple(plan.queries) for plan in wj.plan),
            )
        )
    jobs.seed = workload.seed
    jobs.params = dict(workload.params)
    return jobs
