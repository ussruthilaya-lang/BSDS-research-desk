import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "prototype"))

from sim import Backend, Sim, make_corpus, query_key, search  # noqa: E402


def test_query_key_ignores_case_order_punctuation_and_duplicates():
    assert query_key("Distributed Caching!") == query_key("caching distributed")
    assert query_key("cache cache raft") == query_key("raft cache")
    assert query_key("raft") != query_key("paxos")


def test_search_is_deterministic_and_key_dependent():
    corpus = make_corpus(100)
    assert search(corpus, "raft") == search(corpus, "raft")
    assert search(corpus, "raft") != search(corpus, "paxos")
    assert len(search(corpus, "raft", top=5)) == 5


def test_sim_runs_events_in_time_order_and_fifo_on_ties():
    sim, seen = Sim(), []
    sim.at(2.0, seen.append, "c")
    sim.at(1.0, seen.append, "a")
    sim.at(1.0, seen.append, "b")
    sim.run()
    assert seen == ["a", "b", "c"]
    assert sim.now == 2.0


def test_sim_run_until_stops_before_later_events():
    sim, seen = Sim(), []
    sim.at(1.0, seen.append, "early")
    sim.at(5.0, seen.append, "late")
    sim.run(until=2.0)
    assert seen == ["early"]


def test_backend_paced_calls_have_no_violations():
    sim = Sim()
    backend = Backend(sim, make_corpus(50))
    for i in range(3):
        sim.at(i * 3.0, backend.call, f"q{i}", lambda r: None)
    sim.run()
    assert backend.calls == 3
    assert backend.overlap_violations == 0
    assert backend.pacing_violations == 0


def test_backend_counts_overlap_and_pacing_violations():
    sim = Sim()
    backend = Backend(sim, make_corpus(50))
    sim.at(0.0, backend.call, "a", lambda r: None)
    sim.at(0.5, backend.call, "b", lambda r: None)  # first still in flight, too soon
    sim.run()
    assert backend.overlap_violations == 1
    assert backend.pacing_violations == 1


def test_backend_returns_the_deterministic_result():
    sim, got = Sim(), []
    corpus = make_corpus(50)
    backend = Backend(sim, corpus)
    sim.at(0.0, backend.call, "raft", got.append)
    sim.run()
    assert got == [search(corpus, "raft")]
