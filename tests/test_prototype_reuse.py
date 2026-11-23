"""Cache and in-flight merge for the toy simulation (task S4, single-subagent jobs)."""
import pytest

from gateway import Gateway
from reuse import ReuseLayer
from sim import Backend, Sim, make_corpus, search
from system import run_baseline


def build(mode, ttl_s=600.0, max_queue=50):
    sim = Sim()
    corpus = make_corpus(50)
    backend = Backend(sim, corpus)
    gateway = Gateway(sim, backend, max_queue=max_queue)
    layer = ReuseLayer(sim, gateway, backend, mode=mode, ttl_s=ttl_s)
    return sim, corpus, backend, gateway, layer


def ask(sim, layer, key, at, deadline=1000.0, got=None, dropped=None):
    """Schedule one request; results are appended as (key, time, result) so timing is checkable."""
    got = [] if got is None else got
    dropped = [] if dropped is None else dropped
    sim.at(at, layer.submit, key, deadline, lambda r: got.append((key, sim.now, r)), dropped.append)
    return got, dropped


def test_none_mode_passes_every_request_to_the_gateway():
    sim, corpus, backend, gateway, layer = build("none")
    ask(sim, layer, "raft", 0.0)
    ask(sim, layer, "raft", 0.0)
    sim.run()
    assert backend.calls == 2
    assert (layer.hits, layer.merged) == (0, 0)


def test_cache_serves_a_repeat_with_no_provider_call_and_no_delay():
    sim, corpus, backend, gateway, layer = build("cache")
    got, _ = ask(sim, layer, "raft", 0.0)
    ask(sim, layer, "raft", 10.0, got=got)
    sim.run()
    assert backend.calls == 1
    assert layer.hits == 1
    (_, t1, r1), (_, t2, r2) = got
    assert r1 == r2 == search(corpus, "raft")
    assert t1 == pytest.approx(1.0)  # one provider latency
    assert t2 == pytest.approx(10.0)  # the hit costs nothing


def test_cache_entry_expires_after_the_ttl():
    sim, corpus, backend, gateway, layer = build("cache", ttl_s=30.0)
    ask(sim, layer, "raft", 0.0)
    ask(sim, layer, "raft", 20.0)  # inside the TTL: a hit
    ask(sim, layer, "raft", 40.0)  # past it: fetched again
    sim.run()
    assert backend.calls == 2
    assert layer.hits == 1


def test_cache_without_merge_lets_simultaneous_requests_each_call_the_provider():
    sim, corpus, backend, gateway, layer = build("cache")
    ask(sim, layer, "raft", 0.0)
    ask(sim, layer, "raft", 0.0)
    sim.run()
    assert backend.calls == 2
    assert layer.merged == 0


def test_two_simultaneous_requests_cause_exactly_one_provider_call_when_merging():
    sim, corpus, backend, gateway, layer = build("cache_merge")
    got, _ = ask(sim, layer, "raft", 0.0)
    ask(sim, layer, "raft", 0.0, got=got)
    sim.run()
    assert backend.calls == 1
    assert layer.merged == 1
    assert len(got) == 2 and got[0][2] == got[1][2] == search(corpus, "raft")


def test_first_asker_expiring_does_not_cancel_the_call_for_a_later_waiter():
    sim, corpus, backend, gateway, layer = build("cache_merge")
    ask(sim, layer, "busy", 0.0)  # occupies the provider until the pacer allows the next start at t=3
    first_got, first_dropped = ask(sim, layer, "raft", 0.0, deadline=2.0)  # cannot make a t=3 dispatch
    late_got, late_dropped = ask(sim, layer, "raft", 0.5, deadline=100.0)  # joins the in-flight claim
    sim.run()
    assert first_dropped == ["expired"] and not first_got
    assert not late_dropped
    assert late_got[0][2] == search(corpus, "raft")
    assert backend.calls == 2  # "busy" plus ONE call for raft, made on behalf of the late waiter


def test_a_rejected_claim_fails_cleanly_and_does_not_retry_forever():
    sim, corpus, backend, gateway, layer = build("cache_merge", max_queue=1)
    ask(sim, layer, "busy", 0.0)  # dispatched at once
    ask(sim, layer, "filler", 0.0)  # fills the one-slot queue
    _, dropped = ask(sim, layer, "raft", 0.0)  # the queue is full: rejected
    ask(sim, layer, "raft", 0.0, dropped=dropped)  # the claim was cleared, so this one is rejected too
    sim.run()
    assert dropped == ["rejected", "rejected"]
    assert backend.calls == 2  # busy and filler; raft never reached the provider


def test_a_dropped_claim_is_cleared_so_a_later_request_can_claim_again():
    sim, corpus, backend, gateway, layer = build("cache_merge", max_queue=1)
    ask(sim, layer, "busy", 0.0)
    ask(sim, layer, "filler", 0.0)
    ask(sim, layer, "raft", 0.0)  # rejected while the queue is full
    got, _ = ask(sim, layer, "raft", 20.0)  # the provider is free again: a fresh claim succeeds
    sim.run()
    assert got and got[0][2] == search(corpus, "raft")


def test_reuse_runs_stay_correct_and_never_break_the_provider_limits():
    for mode in ("cache", "cache_merge"):
        r = run_baseline(4, 6, duration_s=900, seed=1, pool_size=30, skew=1.2, reuse_mode=mode)
        assert r["wrong_briefs"] == 0
        assert r["violations"] == 0


def test_default_run_has_no_reuse_and_reports_zero_hits():
    r = run_baseline(2, 3, duration_s=600, seed=2)
    assert (r["cache_hits"], r["merged"]) == (0, 0)


def test_cache_cuts_calls_and_lifts_throughput_when_searches_repeat():
    kwargs = dict(workers=4, rate_per_min=6, duration_s=1800, seed=0, pool_size=30, skew=1.2)
    none = run_baseline(**kwargs)
    cache = run_baseline(reuse_mode="cache", **kwargs)
    assert cache["upstream_calls"] < none["upstream_calls"] / 2
    assert cache["briefs_per_min"] > none["briefs_per_min"]


def test_cache_does_little_when_searches_are_mostly_unique():
    kwargs = dict(workers=4, rate_per_min=3, duration_s=1800, seed=0, pool_size=5000, skew=0.0)
    none = run_baseline(**kwargs)
    cache = run_baseline(reuse_mode="cache", **kwargs)
    assert cache["cache_hits"] <= 0.1 * 5 * 3 * 30  # under 10% of the ~450 searches
    assert cache["upstream_calls"] >= 0.9 * none["upstream_calls"]


def test_merging_beats_cache_alone_on_a_cold_burst():
    kwargs = dict(workers=12, rate_per_min=120, n_questions=24, duration_s=600, seed=0, pool_size=30, skew=1.2)
    cache = run_baseline(reuse_mode="cache", **kwargs)
    merge = run_baseline(reuse_mode="cache_merge", **kwargs)
    assert merge["merged"] > 0
    assert merge["upstream_calls"] < cache["upstream_calls"]
