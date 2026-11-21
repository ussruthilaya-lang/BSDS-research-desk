from gateway import Gateway
from sim import Backend, Sim, make_corpus


def setup(max_queue=50, **backend_kwargs):
    sim = Sim()
    backend = Backend(sim, make_corpus(50), **backend_kwargs)
    return sim, backend, Gateway(sim, backend, max_queue=max_queue)


def test_burst_is_paced_in_fifo_order_without_violations():
    sim, backend, gw = setup()
    starts, order = [], []
    real_call = backend.call

    def spy(key, on_done):
        starts.append(sim.now)
        real_call(key, on_done)

    backend.call = spy
    for i in range(5):
        gw.submit(f"q{i}", 1000.0, lambda r, i=i: order.append(i), lambda reason: None)
    sim.run()
    assert starts == [0.0, 3.0, 6.0, 9.0, 12.0]
    assert order == [0, 1, 2, 3, 4]
    assert backend.overlap_violations == 0
    assert backend.pacing_violations == 0


def test_full_queue_rejects_immediately():
    sim, backend, gw = setup(max_queue=2)
    dropped = []
    for i in range(5):
        gw.submit(f"q{i}", 1000.0, lambda r: None, dropped.append)
    sim.run()
    # first dispatches at once, next two wait in the queue, last two are rejected
    assert dropped == ["rejected", "rejected"]
    assert gw.rejected == 2
    assert backend.calls == 3


def test_request_that_cannot_meet_deadline_is_dropped_without_a_call():
    sim, backend, gw = setup()
    dropped = []
    gw.submit("first", 1000.0, lambda r: None, dropped.append)
    # second would dispatch at t=3 and arrive at t=4, after its deadline of 2.0
    gw.submit("second", 2.0, lambda r: None, dropped.append)
    sim.run()
    assert dropped == ["expired"]
    assert gw.expired == 1
    assert backend.calls == 1


def test_expired_drop_does_not_consume_a_pacing_slot():
    sim, backend, gw = setup()
    starts, real_call = [], backend.call

    def spy(key, on_done):
        starts.append(sim.now)
        real_call(key, on_done)

    backend.call = spy
    gw.submit("a", 1000.0, lambda r: None, lambda reason: None)
    gw.submit("dead", 2.0, lambda r: None, lambda reason: None)
    gw.submit("b", 1000.0, lambda r: None, lambda reason: None)
    sim.run()
    assert starts == [0.0, 3.0]  # b goes at t=3, not t=6


def test_slow_backend_never_overlaps_calls():
    # latency longer than pacing: the in-flight guard must hold calls back
    sim, backend, gw = setup(latency=5.0)
    for i in range(4):
        gw.submit(f"q{i}", 1000.0, lambda r: None, lambda reason: None)
    sim.run()
    assert backend.calls == 4
    assert backend.overlap_violations == 0


def test_max_depth_tracks_deepest_queue():
    sim, backend, gw = setup()
    for i in range(4):
        gw.submit(f"q{i}", 1000.0, lambda r: None, lambda reason: None)
    assert gw.max_depth == 3  # first dispatched immediately, three waiting
