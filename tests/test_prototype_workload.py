import pytest

from workload import make_workload, zipf_weights


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


@pytest.mark.parametrize(
    "overrides",
    [dict(rate_per_min=0), dict(k=0), dict(pool_size=3, k=5), dict(skew=-1)],
)
def test_invalid_arguments_raise(overrides):
    with pytest.raises(ValueError):
        build(**overrides)
