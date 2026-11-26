import pytest

from researchdesk import contracts as c
from sim import query_key
from workload import (
    from_json,
    make_jobs,
    make_workload,
    repeat_fraction,
    repeat_fraction_across,
    repeat_fraction_within,
    to_json,
    zipf_weights,
)


def build(**overrides):
    args = dict(n_questions=50, rate_per_min=10, k=5, pool_size=40, skew=1.0, seed=1)
    args.update(overrides)
    return make_workload(**args)


def test_same_seed_gives_identical_workload_and_different_seed_differs():
    assert build(seed=7) == build(seed=7)
    assert build(seed=7) != build(seed=8)


def test_arrivals_increase_and_deadline_is_arrival_plus_offset():
    questions = build(deadline_s=90.0)
    arrivals = [q.arrival for q in questions]
    assert arrivals == sorted(arrivals)
    assert all(q.deadline == pytest.approx(q.arrival + 90.0) for q in questions)


def test_mean_interarrival_matches_rate():
    questions = build(n_questions=3000, rate_per_min=12, pool_size=10, k=2)
    mean_gap = questions[-1].arrival / len(questions)
    assert mean_gap == pytest.approx(60.0 / 12, rel=0.1)


def test_each_question_has_k_distinct_queries():
    for q in build(k=5, pool_size=6, skew=2.0):  # tight pool + heavy skew stresses this
        assert len(q.queries) == 5
        assert len(set(q.queries)) == 5


def test_zipf_weights_uniform_at_zero_and_decreasing_otherwise():
    assert zipf_weights(4, 0.0) == [1.0, 1.0, 1.0, 1.0]
    weights = zipf_weights(4, 1.0)
    assert weights == sorted(weights, reverse=True)


def test_repeat_fraction_separates_unique_from_repeated_workloads():
    mostly_unique = build(n_questions=100, k=5, pool_size=5000, skew=0.0)
    highly_repeated = build(n_questions=100, k=5, pool_size=30, skew=1.2)
    assert repeat_fraction(mostly_unique) < 0.2
    assert repeat_fraction(highly_repeated) > 0.7


def test_repeat_fraction_is_zero_for_empty_workload():
    assert repeat_fraction([]) == 0.0


@pytest.mark.parametrize(
    "overrides",
    [dict(rate_per_min=0), dict(k=0), dict(pool_size=3, k=5), dict(skew=-1)],
)
def test_invalid_arguments_raise(overrides):
    with pytest.raises(ValueError):
        build(**overrides)


# ------------------------------------------------ job model (task S2) -------


def jobs_for(**overrides):
    args = dict(n_jobs=40, rate_per_min=6, n_subagents=4, k=5, cluster_size=12, pool_size=200, skew=1.0, seed=1)
    args.update(overrides)
    return make_jobs(**args)


def all_queries(job):
    return [q for sub in job.subagents for q in sub]


def test_jobs_same_seed_identical_and_different_seed_differs():
    assert jobs_for(seed=5) == jobs_for(seed=5)
    assert jobs_for(seed=5) != jobs_for(seed=6)


def test_each_job_has_n_subagents_of_k_distinct_queries_from_one_cluster():
    for job in jobs_for(n_subagents=3, k=4, cluster_size=9):
        assert len(job.subagents) == 3
        for sub in job.subagents:
            assert len(sub) == 4 and len(set(sub)) == 4  # a subagent never repeats a search
        assert len(set(all_queries(job))) <= 9  # everything comes from the job's topic cluster


def test_jobs_arrive_in_order_and_deadline_is_relative_to_arrival():
    jobs = jobs_for(deadline_s=90.0)
    assert [j.arrival for j in jobs] == sorted(j.arrival for j in jobs)
    assert all(j.deadline_s == 90.0 and j.deadline == pytest.approx(j.arrival + 90.0) for j in jobs)


def test_mean_job_interarrival_matches_rate():
    jobs = jobs_for(n_jobs=3000, rate_per_min=12)
    assert jobs[-1].arrival / len(jobs) == pytest.approx(60.0 / 12, rel=0.1)


def test_a_smaller_cluster_gives_a_higher_within_job_repeat_fraction():
    tight = repeat_fraction_within(jobs_for(n_subagents=4, k=5, cluster_size=5))
    loose = repeat_fraction_within(jobs_for(n_subagents=4, k=5, cluster_size=60))
    assert tight == pytest.approx(0.75)  # c = k: all 4 subagents ask the same 5, so 15 of 20 searches repeat
    assert loose < tight


def test_within_plus_across_equals_the_global_repeat_fraction():
    for kwargs in (dict(pool_size=30, skew=1.2, cluster_size=8), dict(pool_size=5000, skew=0.0, cluster_size=20)):
        jobs = jobs_for(**kwargs)
        seen, repeats, total = set(), 0, 0
        for job in jobs:
            for q in all_queries(job):
                repeats += query_key(q) in seen
                seen.add(query_key(q))
                total += 1
        within, across = repeat_fraction_within(jobs), repeat_fraction_across(jobs)
        assert within + across == pytest.approx(repeats / total)


def test_a_small_hot_pool_raises_the_across_job_repeat_fraction():
    hot = repeat_fraction_across(jobs_for(pool_size=30, skew=1.2, cluster_size=8))
    cold = repeat_fraction_across(jobs_for(pool_size=5000, skew=0.0, cluster_size=8))
    assert hot > cold + 0.3


def test_repeat_fractions_are_zero_for_no_jobs():
    assert repeat_fraction_within([]) == 0.0 and repeat_fraction_across([]) == 0.0


def test_workload_file_passes_the_contract_and_round_trips_exactly():
    jobs = jobs_for(seed=3)
    text = to_json(jobs, seed=3, params={"duration_s": 600})
    wf = c.WorkloadFile.from_json(text)  # the contract's own parser accepts it
    assert wf.seed == 3 and len(wf.jobs) == len(jobs)
    assert wf.params["duration_s"] == 600  # Muskan's harness reads its measurement window from here
    assert (wf.params["n_subagents"], wf.params["k"], wf.params["cluster_size"]) == (4, 5, 12)
    assert from_json(text) == jobs  # exact, including float arrival times


def test_workload_file_deadline_is_relative_and_plan_ids_are_zero_based():
    jobs = jobs_for(deadline_s=75.0, n_jobs=3)
    wf = c.WorkloadFile.from_json(to_json(jobs, seed=0))
    for wj, job in zip(wf.jobs, jobs):
        assert wj.deadline_s == 75.0 and wj.arrival_s == job.arrival
        assert [p.subagent_id for p in wj.plan] == list(range(len(job.subagents)))
    assert len({wj.job_id for wj in wf.jobs}) == len(jobs)


def test_workload_file_params_record_how_the_jobs_were_made():
    jobs = jobs_for(skew=1.2, pool_size=30, rate_per_min=9, deadline_s=60.0)
    params = c.WorkloadFile.from_json(to_json(jobs, seed=1)).params
    assert (params["pool_size"], params["skew"], params["rate_per_min"], params["deadline_s"]) == (30, 1.2, 9, 60.0)


@pytest.mark.parametrize(
    "overrides",
    [
        dict(n_subagents=0), dict(k=0), dict(cluster_size=3, k=5), dict(pool_size=4, cluster_size=12),
        dict(rate_per_min=0), dict(skew=-1), dict(n_jobs=-1), dict(deadline_s=0),
    ],
)
def test_make_jobs_rejects_bad_arguments(overrides):
    with pytest.raises(ValueError):
        jobs_for(**overrides)


def test_replay_harness_can_build_job_api_requests_from_the_generated_file():
    """Cross-lane check (M6): the file from to_json is what harness/replay.py replays."""
    pytest.importorskip("redis")  # harness.replay imports it; the dev extra installs it
    from harness import replay

    jobs = jobs_for(n_subagents=3, k=4, cluster_size=9, deadline_s=80.0, n_jobs=5)
    workload = c.WorkloadFile.from_json(to_json(jobs, params={"duration_s": 300}))
    assert workload.params["duration_s"] == 300
    for wj, job in zip(workload.jobs, jobs):
        request = c.JobRequest.from_dict(replay.job_request(wj, "run1"))  # the API would accept it
        assert request.deadline_ms == 80_000 and request.client == "harness"
        assert [p.queries for p in request.plan] == [list(sub) for sub in job.subagents]
        assert replay.post_delay_s(wj, 0.1) == pytest.approx(job.arrival * 0.1)
