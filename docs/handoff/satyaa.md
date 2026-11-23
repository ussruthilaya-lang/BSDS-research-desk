# Handoff: Satyaa

**Lane:** provider simulator, gateway, admission control, task leases and crash recovery, the MCP
server, and the Mode B demo. **Leads E4** (crash recovery).

Read `CLAUDE.md` (shared rules) and `docs/contracts.md` §1 to §5, §7, §8 (leases and the
interfaces table), §10 and §11 before starting.

## What you produce for the others

| Thing | Contract section | Used by |
|---|---|---|
| Skeletons with only `GET /health` for provider, gateway and mcp, by **Wed 11/25** | §1 | Muskan's Compose (M5) |
| Provider simulator service (port 8001): `POST /search`, `GET /stats`, `POST /faults`, `POST /reset` | §4 | your gateway; Muskan's harness reads `GET /stats` for `upstream_calls` and `violations` in E1, E2, E4 |
| Gateway service (port 8002): `POST /dispatch`, `POST /admit`; writes `rd:corpus_version` | §5 | Sruthilaya's `search_once` (dispatch, staleness), Muskan's Job API (admission) |
| Versioned corpus and latency jitter in `prototype/sim.py` | §4 | Sruthilaya's cache staleness in the simulator (S4) |
| Admission control, `fifo` / `round_robin` / `fair_user`, and per-user quotas (`user_quota`) | §5 | Muskan's E1 (M9); the public service |
| Lease code `src/researchdesk/workflow/lease.py`: `claim`, `heartbeat`, `ack`; honours `RD_LEASES` | §8 Leases, interfaces table | Muskan's worker (M4) |
| The public MCP service: `streamable-http` at `POST /mcp/u/{user}` behind the Cloudflare tunnel, for anyone's Claude Desktop or Claude Code; `stdio` for local development; optional progress card | §7 | the demo, anyone who connects |
| Events `gateway.*`, `provider.*`, `task.lease_expired`, `task.reclaimed`; metrics `rd_gateway_*`, `rd_provider_*`, `rd_admission_total`, `rd_lease_expiries_total` (via `events.count`) | §10, §11 | Muskan's dashboard and live control room |

## What you need from the others

| Thing | From | Target | Until it lands |
|---|---|---|---|
| `events.emit` and `events.count` | Muskan (M7a) | Wed 11/25 | print the event's JSON line only |
| `runner.resume_step` and the checkpoint keys `rd:ckpt:...` | Sruthilaya (S7) | Thu 12/3 | write checkpoints and count them in your own test |
| Job API `POST /jobs`, `GET /jobs/{job_id}`, `POST /search` | Muskan (M3) | Sun 11/29 | MCP tools return a fixed stub reply |
| Worker process calling your lease code | Muskan (M4) | Wed 12/2 | test leases with a fake worker loop |
| Replay harness | Muskan (M6) | Wed 12/2 | run E4 by hand with a small workload |
| Live control room | Muskan (M12) | Sat 12/5 | read `GET /stats` and the event stream directly |

## Your tasks, in order

| ID | Task | Files | Target | Done when |
|---|---|---|---|---|
| T2 | HW9 sections 1, 4, 5; assemble the PDF and submit | shared draft | **Mon 11/23, 12:00 pm** | Submitted; screenshot in the team chat |
| T3 | Review contract §2, §4, §5, §7 and the lease part of §8; approve the PR | `docs/contracts.md` | Tue 11/24 | PR merged with all three approvals |
| T10 | Rewrite `README.md` and `docs/PLAN.md` to the v2 design and the E1 to E4 numbering | `README.md`, `docs/PLAN.md` | Tue 11/24 | Merged; no v1 numbering left |
| T1 | Versioned corpus and seeded latency jitter in the simulator, per §4 | `prototype/sim.py`, `tests/test_prototype_sim.py` | Wed 11/25 | Same seed gives the same latencies; at version 0 the ranking equals the old `search()`; after a bump the version is higher and results change; every old test and the E1 baseline test pass |
| T4 | Provider simulator service per §4 (skeleton by Wed 11/25) | `src/researchdesk/simulator/`, Dockerfile | Fri 11/27 | Two direct calls closer than `RD_PACING_MS` show `pacing_violations` = 1 in `GET /stats`; with `slowdown` 2.0, the median latency of 10 calls is at least 1.8 × the median without faults; `POST /reset` zeroes that run's counters |
| T5 | Gateway service per §5: one dispatcher loop, bounded queue, one call in flight, pacing plus `RD_PACING_SAFETY_REAL_MS`, p95 deadline check, retry backoff, drop reasons; writes `rd:corpus_version` (skeleton by Wed 11/25) | `src/researchdesk/gateway/`, Dockerfile | Sun 11/29 | A burst of 20 requests leaves 0 violations; a request whose deadline cannot be met is dropped and the provider's `calls` count does not change |
| T6 | Admission control (`POST /admit`, the §5 estimate), the `fifo` / `round_robin` / `fair_user` switch, and per-user quotas (`RD_USER_CALLS_PER_MIN`, `RD_USER_QUEUE_MAX`, drop reason `user_quota`, reply 429): simulator first, then the service | `prototype/gateway.py`, `src/researchdesk/gateway/` | Wed 12/2 | (a) With the E1 baseline settings (4 workers, k = 5, 120 s deadline, 8 s think time, seeds 0 to 2, 12 arrivals a minute), median wasted calls with admission on are lower than with it off. (b) With `RD_USER_CALLS_PER_MIN=8` and `fair_user`, a user sending 30 searches a minute gets at most 8 calls in any minute and the rest dropped with `user_quota`, while a second user sending 5 a minute gets all 5 through |
| T12 | The public MCP service per §7: a thin wrapper over `streamable-http`, `POST /mcp/u/{user}` setting `user` (400 for a bad handle), `RD_PUBLIC_HOST` accepted, plain JSON replies; `stdio` for local development; `client` = `claude`; tool descriptions written for Claude | `src/researchdesk/mcp/` | Tue 12/1 | Through the tunnel URL, a Claude Desktop custom connector and `claude mcp add --transport http` both list the three tools; `start_research` returns a job id from the Job API and `get_research` returns its `JobView` (stub or real); two handles show up as two different `user` values in the events |
| T12b | Optional: MCP App progress card `ui://researchdesk/progress.html` on `start_research` and `get_research` (§7) | `src/researchdesk/mcp/ui/` | Sat 12/5 | In the Desktop Chat tab, `start_research` shows the card; its bars move as subagents finish and stop at the final status; a host without MCP Apps gets the same data as text |
| T7 | Task leases per §8: heartbeat key per worker; with `RD_LEASES=on`, reclaim a pending task only when its owner's `rd:hb:{worker_id}` has expired; `attempt` from the delivery count; resume at `runner.resume_step`; acknowledge only when done | `src/researchdesk/workflow/lease.py` | Sat 12/5 | `docker kill` on a worker mid-subagent: with leases on, the job finishes and finished steps make no repeat provider calls; with leases off, that subagent never finishes; a healthy subagent running longer than `RD_LEASE_MS` is never reclaimed |
| T8 | **E4:** `RD_LEASES` off vs on; lease lengths 5000, 10000 and 20000 ms (proposed); 3 seeds; Compose, then a few AWS points. Recovery time from events (§10) | `experiments/e4/` | Sun 12/6 | CSV and a figure of recovery time and duplicate provider calls against lease length |
| T13 | Demo and backup video of the live service, with the live control room in a browser beside it. Scene 1: two people on two different laptops add the tunnel URL with their own handles in Claude Desktop and ask research questions at once (Mode A, with the card if T12b is done). Scene 2: the Desktop Code tab runs four subagents limited to `search_papers` (Mode B). Scene 3: one handle floods the service and gets `user_quota` while the other keeps its share. Never during a measured run | `docs/demo.md`, a demo script | Wed 12/9 | Video in the shared drive; it shows two users, a finished brief, at least one merged call, a `user_quota` drop for the flooding handle only, and violations at 0 |
| T11 | Report sections for the gateway, failure handling and E4; lead the slides and the rehearsal | `docs/` | Wed 12/9 | In the shared draft; one rehearsal done |
| T9 | Future work, not promised: E5 fairness, E6 gateway failover with a fencing token | `experiments/e5/`, `experiments/e6/` | none (only after T1 to T13) | Results, or a note in the report on why it was left out |

Already done: T0 (plan sent to the team), T0b (any programming language is allowed, per Satyaa).

## Watch-outs

- **The gateway is the only thing that paces.** If the provider reports a violation during a normal
  run, the bug is in the gateway or something bypassing it.
- `POST /dispatch` holds the request open until the result or a drop; callers need an HTTP timeout
  longer than their deadline.
- A `deadline_unmeetable` drop must not use a pacing slot (the prototype already does this).
- **The public MCP service** reuses what LeaseBoston learned (`~/Projects/LeaseBoston/README.md`):
  start `cloudflared` first to learn the hostname, then start the server with that hostname in
  `RD_PUBLIC_HOST`; answer with plain JSON because quick tunnels do not support Server-Sent Events.
  The URL changes on every tunnel restart. Check the official Python SDK's docs
  (py.sdk.modelcontextprotocol.io) for the install command and server setup.
- **No login:** a handle in `/mcp/u/{user}` is not proof of identity. Say so in the report, and list
  OAuth 2.1 as future work. Limiting a
  Claude Code subagent to one tool of a server was not checked; try it early, and if it fails, put
  `search_papers` in its own small MCP server.
- **Leases:** decide liveness from the heartbeat key, never from stream idle time alone. A healthy
  subagent (k steps of 8 s thinking plus queueing) sits idle on the stream for longer than
  `RD_LEASE_MS`. `XAUTOCLAIM` (Redis 6.2 and later) can still do the transfer once the heartbeat key
  has expired; read the Redis docs for its exact behaviour.

## Start here

1. Tonight: HW9 (T2). Submit before 12:00 pm Monday.
2. Review your contract sections (T3); push the three `/health` skeletons by Wed 11/25.
3. T1 in `prototype/sim.py`, tests first; T4 needs nothing from anyone else.
