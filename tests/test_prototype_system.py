import math

import pytest

from gateway import Gateway
from sim import Backend, Sim, make_corpus
from system import System, p95, run_baseline
from workload import Question


def build(workers=1, think_time=1.0, **gw):
    sim = Sim()
    corpus = make_corpus(50)
    backend = Backend(sim, corpus)
    gateway = Gateway(sim, backend, **gw)
    return sim, backend, gateway, System(sim, gateway, corpus, workers, think_time=think_time)


def test_single_question_timeline_and_correctness():
    sim, backend, gateway, system = build(think_time=1.0)
    system.load([Question(0, 0.0, 100.0, ("a one", "b two", "c three"))])
    sim.run()
    # calls start at 0, 3, 6 (paced); each result is followed by 1 s of think time
    (outcome,) = system.outcomes
    assert outcome.status == "on_time"
    assert outcome.finish == pytest.approx(8.0)
    assert outcome.correct
    assert backend.calls == 3


def test_question_waiting_too_long_for_a_worker_expires_without_calls():
    sim, backend, gateway, system = build(think_time=1.0)
    system.load(
        [
            Question(0, 0.0, 100.0, ("a", "b", "c")),
            Question(1, 0.0, 5.0, ("x", "y")),  # worker busy until t=8, deadline is 5
        ]
    )
    sim.run()
    statuses = {o.qid: o.status for o in system.outcomes}
    assert statuses == {0: "on_time", 1: "expired"}
    assert backend.calls == 3


def test_finishing_after_deadline_is_late_not_on_time():
    sim, backend, gateway, system = build(think_time=5.0)
    # last result arrives at t=1, think time pushes finish to t=6, past the deadline of 3
    system.load([Question(0, 0.0, 3.0, ("a",))])
    sim.run()
    assert system.outcomes[0].status == "late"


def test_rejected_search_aborts_question_and_frees_the_worker():
    sim, backend, gateway, system = build(workers=3, think_time=1.0, max_queue=0)
    system.load([Question(i, 0.0, 100.0, ("a", "b")) for i in range(3)])
    sim.run()
    assert sorted(o.status for o in system.outcomes) == ["rejected"] * 3
    assert system.free_slots == 3


def test_p95_nearest_rank():
    assert p95(list(range(1, 101))) == 95
    assert p95([7.0]) == 7.0
    assert math.isnan(p95([]))


def test_baseline_run_is_reproducible_and_violation_free():
    a = run_baseline(workers=2, rate_per_min=3, duration_s=600, seed=4)
    b = run_baseline(workers=2, rate_per_min=3, duration_s=600, seed=4)
    assert a == b
    assert a["violations"] == 0
    assert a["wrong_briefs"] == 0


def test_throughput_never_exceeds_provider_ceiling():
    # 20 calls/min and 5 calls per brief: at most 4 briefs/min, however hard we push
    result = run_baseline(workers=4, rate_per_min=12, k=5, duration_s=1800, seed=1)
    assert result["briefs_per_min"] <= 4.0 + 1e-9
    assert result["violations"] == 0


def test_overload_builds_a_worker_backlog_and_wastes_calls():
    light = run_baseline(workers=4, rate_per_min=2, duration_s=1800, seed=3)
    heavy = run_baseline(workers=4, rate_per_min=12, duration_s=1800, seed=3)
    assert heavy["max_pending"] > 10 * max(light["max_pending"], 1)
    assert heavy["wasted_calls"] > light["wasted_calls"]
    assert heavy["wasted_calls"] >= 0


def test_more_workers_help_below_the_ceiling():
    low = run_baseline(workers=1, rate_per_min=3, duration_s=1800, seed=2)
    high = run_baseline(workers=2, rate_per_min=3, duration_s=1800, seed=2)
    assert high["briefs_per_min"] > low["briefs_per_min"]
