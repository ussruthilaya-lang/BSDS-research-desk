"""Fan-out and gather in the simulator (task S3): subagent tasks, plan and synth time, gather policies.

Timelines in the comments are worked out by hand from: provider latency 1 s, calls started at least
3 s apart, one call in flight, think time after every result.
"""
import math

import pytest

from researchdesk import contracts as c
from gateway import Gateway
from reuse import ReuseLayer
from sim import Backend, Sim, make_corpus, search
from system import (
    DEFAULT_MARGIN, DEFAULT_PLAN_TIME, DEFAULT_SYNTH_TIME, System, csv_row, job_status, run_jobs,
)
from workload import Job


def build(slots=1, think_time=8.0, max_queue=50, **system_kwargs):
    sim = Sim()
    corpus = make_corpus(50)
    backend = Backend(sim, corpus)
    gateway = Gateway(sim, backend, max_queue=max_queue)
    system = System(sim, gateway, corpus, 1, slots_per_worker=slots, think_time=think_time, **system_kwargs)
    return sim, corpus, backend, gateway, system


def job(subagents, deadline_s=100.0, arrival=0.0, job_id=0):
    return Job(job_id, arrival, deadline_s, tuple(tuple(s) for s in subagents))


def only(system):
    (outcome,) = system.outcomes
    return outcome


# ------------------------------------------------------- final status rules -----


def test_job_status_on_time_late_and_the_nothing_finished_cases():
    assert job_status(done=2, failure_reasons=[], brief_time=10.0, deadline=20.0) == "on_time"
    assert job_status(2, [], 20.0, 20.0) == "on_time"  # exactly at the deadline still counts
    assert job_status(2, [], 21.0, 20.0) == "late"
    assert job_status(1, ["rejected"], 10.0, 20.0) == "on_time"  # a partial brief is still a brief
    assert job_status(0, [], 5.0, 20.0) == "expired"
    assert job_status(0, [None], 5.0, 20.0) == "expired"  # still running when the gather stopped
    assert job_status(0, ["expired", "expired"], 5.0, 20.0) == "expired"
    assert job_status(0, ["rejected"], 5.0, 20.0) == "failed"
    assert job_status(0, ["expired", "rejected"], 5.0, 20.0) == "failed"


# ------------------------------------------------------------- timelines -------


def test_plan_and_synth_time_wrap_the_subagent_work():
    sim, corpus, backend, gateway, system = build(think_time=1.0, plan_time=2.0, synth_time=4.0)
    system.load([job([["a"]])])
    sim.run()
    # plan to t=2; call 2 to 3; think to 4 (task done); synth to 8 (brief written)
    outcome = only(system)
    assert outcome.status == "on_time"
    assert outcome.finish == pytest.approx(8.0)
    assert outcome.latency == pytest.approx(8.0)
    assert outcome.completeness == 1.0


def test_subagents_run_in_parallel_on_free_slots_and_one_after_another_on_one_slot():
    three = [["a"], ["b"], ["c"]]
    sim, corpus, backend, gateway, system = build(slots=3)
    system.load([job(three)])
    sim.run()
    # calls start at 0, 3, 6 (paced), results at 1, 4, 7, each followed by 8 s of thinking
    assert only(system).finish == pytest.approx(15.0)

    sim, corpus, backend, gateway, system = build(slots=1)
    system.load([job(three)])
    sim.run()
    # one slot: 0 to 9, 9 to 18, 18 to 27
    assert only(system).finish == pytest.approx(27.0)


def test_a_job_reports_one_outcome_with_completeness_one_when_every_subagent_finishes():
    sim, corpus, backend, gateway, system = build(slots=2)
    system.load([job([["a", "b"], ["c", "d"]])])
    sim.run()
    outcome = only(system)
    assert (outcome.status, outcome.completeness, outcome.n_subagents) == ("on_time", 1.0, 2)
    assert outcome.correct


# --------------------------------------------------------- gather policies -----


def slow_job_setup(gather, synth_time):
    """Two subagents of two searches on ONE slot, so the second subagent is the slow one.

    A is done at t=18 and B at t=36. Deadline 30, margin 5.
    """
    sim, corpus, backend, gateway, system = build(slots=1, gather=gather, synth_time=synth_time, margin=5.0)
    system.load([job([["a", "b"], ["c", "d"]], deadline_s=30.0)])
    sim.run()
    return only(system), backend


def test_deadline_partial_returns_an_on_time_partial_brief_when_a_subagent_is_slow():
    outcome, backend = slow_job_setup("deadline_partial", synth_time=2.0)
    # stops at deadline - margin = 25 with only A done, writes the brief until 27, before the deadline of 30
    assert outcome.status == "on_time"
    assert outcome.completeness == pytest.approx(0.5)
    assert outcome.finish == pytest.approx(27.0)
    assert outcome.correct
    assert backend.overlap_violations == 0 and backend.pacing_violations == 0


def test_wait_all_waits_for_the_slow_subagent_and_the_brief_is_late():
    outcome, _ = slow_job_setup("wait_all", synth_time=2.0)
    # B is done at 36, the brief is written at 38, after the deadline of 30
    assert outcome.status == "late"
    assert outcome.completeness == 1.0
    assert outcome.finish == pytest.approx(38.0)


def test_everything_finishing_before_the_margin_does_not_wait_for_the_timer():
    sim, corpus, backend, gateway, system = build(slots=1, gather="deadline_partial", synth_time=2.0, margin=5.0)
    system.load([job([["a"]], deadline_s=100.0)])
    sim.run()
    # task done at 9; the margin timer would only fire at 95, but the gather stops as soon as all are done
    assert only(system).finish == pytest.approx(11.0)


# ------------------------------------------------------- failures and drops ----


def test_a_dropped_search_fails_only_its_own_subagent():
    # max_queue=1 with three simultaneous searches: one is dispatched, one queues, one is rejected
    sim, corpus, backend, gateway, system = build(slots=3, max_queue=1)
    system.load([job([["a"], ["b"], ["c"]])])
    sim.run()
    outcome = only(system)
    assert outcome.status == "on_time"
    assert outcome.completeness == pytest.approx(2 / 3)
    assert outcome.correct  # only the finished subagents are in the brief, and they are right


def test_a_job_whose_searches_are_all_rejected_is_failed_not_rejected():
    sim, corpus, backend, gateway, system = build(slots=3, max_queue=0)
    system.load([job([["a"], ["b"], ["c"]])])
    sim.run()
    outcome = only(system)
    assert (outcome.status, outcome.completeness) == ("failed", 0.0)
    assert system.free_slots == 3  # the slots are free again


def test_a_job_that_never_gets_a_slot_in_time_expires_without_calls():
    sim, corpus, backend, gateway, system = build(slots=1)
    system.load([job([["a", "b"]], deadline_s=100.0, job_id=0), job([["x"]], deadline_s=5.0, job_id=1)])
    sim.run()
    statuses = {o.qid: o.status for o in system.outcomes}
    assert statuses == {0: "on_time", 1: "expired"}
    assert backend.calls == 2


# --------------------------------------------- call ids and wasted calls --------


def test_results_carry_the_id_of_the_provider_call_that_made_them():
    sim = Sim()
    corpus = make_corpus(50)
    backend = Backend(sim, corpus)
    got = []
    sim.at(0.0, backend.call, "raft", got.append)
    sim.at(3.0, backend.call, "paxos", got.append)
    sim.run()
    assert [r.call_id for r in got] == [1, 2]
    assert got[0] == search(corpus, "raft")  # still equal to a plain tuple of paper ids


def test_a_cache_hit_keeps_the_call_id_of_the_call_that_filled_the_cache():
    sim = Sim()
    corpus = make_corpus(50)
    backend = Backend(sim, corpus)
    layer = ReuseLayer(sim, Gateway(sim, backend), backend, mode="cache")
    got = []
    sim.at(0.0, layer.submit, "raft", 1000.0, got.append, lambda r: None)
    sim.at(10.0, layer.submit, "raft", 1000.0, got.append, lambda r: None)
    sim.run()
    assert [r.call_id for r in got] == [1, 1]


def small_run(**overrides):
    args = dict(
        workers=2, rate_per_min=2, n_subagents=2, k=2, cluster_size=2, pool_size=30, skew=1.0,
        duration_s=300, n_jobs=1, seed=0,
    )
    args.update(overrides)
    return run_jobs(**args)


def test_reuse_serves_two_subagents_with_one_call_per_distinct_search_and_wastes_nothing():
    none = small_run(reuse_mode="none")
    merged = small_run(reuse_mode="cache_merge")
    assert (none["on_time_correct"], merged["on_time_correct"]) == (1, 1)
    assert none["upstream_calls"] == 4 and none["wasted_calls"] == 0
    # both subagents ask the same two searches (cluster = k), so two calls serve all four steps
    assert merged["upstream_calls"] == 2 and merged["wasted_calls"] == 0
    assert merged["cache_hits"] + merged["merged"] == 2


def test_calls_for_a_job_that_cannot_finish_are_all_wasted():
    result = small_run(n_subagents=10, k=5, cluster_size=20, deadline_s=20.0, workers=10, gather="wait_all")
    assert result["on_time_correct"] == 0
    assert result["upstream_calls"] > 0
    assert result["wasted_calls"] == result["upstream_calls"]


# ------------------------------------------------------- the metrics summary ---


def test_summary_has_every_contract_csv_column_in_order():
    result = small_run()
    needed = set(c.HARNESS_CSV_COLUMNS) - {"run_id", "setting", "seed"}
    assert needed <= set(result), sorted(needed - set(result))
    row = csv_row(result, run_id="r1", setting="workers=2", seed=0)
    assert list(row) == list(c.HARNESS_CSV_COLUMNS)
    assert (row["run_id"], row["setting"], row["seed"]) == ("r1", "workers=2", 0)


def test_complete_briefs_count_only_completeness_one_and_never_exceed_all_briefs():
    full = small_run()
    assert full["complete_briefs_per_min"] == pytest.approx(full["briefs_per_min"])  # one job, finished
    partial = run_jobs(
        workers=1, rate_per_min=2, n_subagents=2, k=2, cluster_size=4, pool_size=30, skew=1.0, duration_s=300,
        n_jobs=1, deadline_s=30.0, gather="deadline_partial", think_time=8.0, seed=0,
    )
    assert partial["briefs_per_min"] >= partial["complete_briefs_per_min"]
    assert partial["on_time_correct"] == 1 and partial["complete_briefs_per_min"] == 0
    assert partial["completeness_mean"] == pytest.approx(0.5)


def test_runs_are_reproducible_correct_and_never_break_the_provider_limits():
    for gather in ("wait_all", "deadline_partial"):
        for mode in ("none", "cache_merge"):
            kwargs = dict(workers=4, rate_per_min=4, n_subagents=3, k=3, cluster_size=6, pool_size=30, skew=1.2,
                          duration_s=900, seed=2, gather=gather, reuse_mode=mode)
            a, b = run_jobs(**kwargs), run_jobs(**kwargs)
            assert a == b or all(
                x == y or (isinstance(x, float) and math.isnan(x) and math.isnan(y)) for x, y in zip(a.values(), b.values())
            )
            assert a["wrong_briefs"] == 0 and a["violations"] == 0


def test_a_slower_provider_lowers_completeness_under_deadline_partial():
    kwargs = dict(workers=4, rate_per_min=4, n_subagents=4, k=3, cluster_size=6, pool_size=200, skew=1.0,
                  duration_s=900, seed=1, gather="deadline_partial")
    normal, slow = run_jobs(**kwargs), run_jobs(slowdown=5.0, **kwargs)
    assert slow["completeness_mean"] < normal["completeness_mean"]
    assert slow["violations"] == 0


# ------------------------------------------------------------- settings -------


def test_defaults_match_the_contract_settings():
    s = c.Settings()
    assert DEFAULT_PLAN_TIME * 1000 == s.plan_ms
    assert DEFAULT_SYNTH_TIME * 1000 == s.synth_ms
    assert DEFAULT_MARGIN * 1000 == s.gather_margin_ms


def test_bad_gather_settings_are_rejected():
    sim, corpus, backend, gateway, _ = build()
    with pytest.raises(ValueError):
        System(sim, gateway, corpus, 1, gather="whenever")
    with pytest.raises(ValueError):
        System(sim, gateway, corpus, 1, synth_time=6.0, margin=5.0)  # the brief must fit inside the margin
