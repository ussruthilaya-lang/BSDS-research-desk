"""Cache and in-flight merge in front of the gateway (toy simulation, task S4).

`ReuseLayer.submit` has the same signature as `Gateway.submit`, so the system can use either.

Modes (the same names as the contract's RD_REUSE_MODE):
  none         every search goes to the gateway
  cache        a recent result is reused; simultaneous identical searches each call the provider
  cache_merge  also, identical searches that arrive while one is in flight share that one call

Merge rules, as in docs/contracts.md section 8:
  * the shared call carries the latest deadline among its waiters at the moment it starts, and
    that deadline is fixed from then on (a later waiter cannot extend it)
  * the first asker giving up does not cancel the call for a later waiter
  * if the call is dropped for its deadline, waiters that can still make it claim again together
  * a call rejected because the queue is full fails its waiters at once, with no retry

Not modelled yet: corpus versions, so cached answers can never be stale here.
"""
from dataclasses import dataclass

from sim import Backend, Sim

MODES = ("none", "cache", "cache_merge")


@dataclass
class _Waiter:
    deadline: float
    on_result: object  # callable(result)
    on_drop: object  # callable(reason)


class ReuseLayer:
    def __init__(self, sim: Sim, gateway, backend: Backend, mode: str = "cache_merge", ttl_s: float = 600.0):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        self.sim = sim
        self.gateway = gateway
        self.backend = backend
        self.mode = mode
        self.ttl_s = ttl_s
        self.cache: dict[str, tuple[object, float]] = {}  # key -> (result, time stored)
        self.inflight: dict[str, list[_Waiter]] = {}  # key -> waiters (cache_merge only)
        self.hits = 0
        self.merged = 0

    def submit(self, key: str, deadline: float, on_result, on_drop) -> None:
        if self.mode == "none":
            self.gateway.submit(key, deadline, on_result, on_drop)
            return
        hit = self._lookup(key)
        if hit is not None:
            self.hits += 1
            self.sim.after(0.0, on_result, hit)  # scheduled, not called, like every other result
            return
        if self.mode == "cache":
            self.gateway.submit(key, deadline, lambda res: self._store_then(key, res, on_result), on_drop)
            return
        waiter = _Waiter(deadline, on_result, on_drop)
        if key in self.inflight:
            self.inflight[key].append(waiter)
            self.merged += 1
            return
        self.inflight[key] = [waiter]
        self._claim(key)

    def _lookup(self, key: str):
        entry = self.cache.get(key)
        if entry is None:
            return None
        result, stored_at = entry
        if self.sim.now - stored_at < self.ttl_s:
            return result
        del self.cache[key]
        return None

    def _store_then(self, key: str, result, on_result) -> None:
        self.cache[key] = (result, self.sim.now)
        on_result(result)

    def _claim(self, key: str) -> None:
        """Send one gateway request on behalf of everyone waiting on `key`."""
        deadline = max(w.deadline for w in self.inflight[key])
        self.gateway.submit(
            key,
            deadline,
            on_result=lambda res: self._resolve(key, res),
            on_drop=lambda reason: self._dropped(key, reason),
        )

    def _resolve(self, key: str, result) -> None:
        self.cache[key] = (result, self.sim.now)
        for w in self.inflight.pop(key, []):
            self.sim.after(0.0, w.on_result, result)

    def _dropped(self, key: str, reason: str) -> None:
        waiters = self.inflight.pop(key, [])
        if reason == "rejected":  # queue full: asking again at once would only be rejected again
            for w in waiters:
                w.on_drop(reason)
            return
        can_retry = [w for w in waiters if self.sim.now + self.backend.latency <= w.deadline]
        retry_ids = {id(w) for w in can_retry}
        for w in waiters:
            if id(w) not in retry_ids:
                w.on_drop(reason)
        if can_retry:
            self.inflight[key] = can_retry
            self._claim(key)
