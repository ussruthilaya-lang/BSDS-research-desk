# Research Desk contracts (version 1)

Drafted 2026-11-22 by Satyaa (with Claude) for review. Owners: Satyaa (provider, gateway, MCP,
leases), Sruthilaya (Redis keys, runner, lead), Muskan (Job API, events, metrics). **Nothing here is
final until all three approve the PR** (tasks S6, T3, M2).

The same names live in code in `src/researchdesk/contracts.py` (module `researchdesk.contracts`).
Import from there; never retype a name. `tests/test_contracts.py` fails if this file and that module disagree.

**Changing the contract:** one PR that edits this file, `contracts.py` and the tests together,
approved by all three. A breaking change bumps `CONTRACT_VERSION`. Record it in
`docs/project-management/LOG.md`.

## 1. Services

Docker Compose (task M5) runs every row of this table.

| Service | Port | Owner | Endpoints |
|---|---|---|---|
| api (Job API) | 8000 | Muskan | `POST /jobs`, `GET /jobs/{job_id}`, `GET /jobs/{job_id}/trace`, `POST /search`, `GET /health`, `GET /metrics` |
| provider (simulator) | 8001 | Satyaa | `POST /search`, `GET /stats`, `POST /faults`, `POST /reset`, `GET /health`, `GET /metrics` |
| gateway | 8002 | Satyaa | `POST /dispatch`, `POST /admit`, `GET /health`, `GET /metrics` |
| mcp (thin wrapper, public) | 8003 | Satyaa | `POST /mcp`, `POST /mcp/u/{user}` (MCP Streamable HTTP, public through a tunnel, §7) |
| board (live control room) | 8004 | Muskan | `GET /`, `GET /events/stream`, `GET /health` |
| worker (no HTTP) | — | Muskan (process), Sruthilaya (runner), Satyaa (leases) | reads `rd:tasks` |
| redis | 6379 | Muskan (Compose) | shared state, task stream, event stream |

Every HTTP service answers `GET /health` with `{"status": "ok", "service": NAME, "contract_version": "1"}`.
Each owner pushes a skeleton by **Wed 11/25** so Compose can start it: an HTTP service answers only
`GET /health`; the worker skeleton starts, emits `worker.started` and idles. Compose also runs
prometheus and grafana for task M7.
Services with an HTTP server serve Prometheus text on `GET /metrics` (not the board or mcp).

**Uptime: live on demand.** On the AWS Learner Lab the stack runs while a lab session is running
(End Lab stops the EC2 instances), so the public service is up for testing, the demo and the
presentation, not around the clock.

## 2. Time and the clock

- **Names say which clock.** A name ending in `_ms` (except `_at_ms`) is a **duration or deadline
  in simulated ms**: `deadline_ms`, `latency_ms`, `queue_wait_ms`, every `RD_*_MS` setting. A name
  ending in `_at_ms`, and `ts_ms`, is an **absolute time in real ms on the shared clock**. The one
  exception is `RD_PACING_SAFETY_REAL_MS`, a real-ms duration, as its name says.
- A service multiplies a simulated duration by `RD_TIME_SCALE` only when it sleeps or waits
  (`to_real_ms`), and divides a measured real duration by it (`to_sim_ms`). With
  `RD_TIME_SCALE=0.1`, the 3000 ms pacing gap is 300 real ms.
- **The shared clock is Redis `TIME`** (`redis_time_to_ms`). No service compares its own wall clock
  with another machine's.
- **Over HTTP, deadlines travel as remaining time** (`deadline_ms`). A receiver subtracts the time
  it spent queueing before passing a deadline on. Inside Redis, deadlines are stored as
  `deadline_at_ms` on the shared clock.
- **Only the gateway paces provider calls.** It adds `RD_PACING_SAFETY_REAL_MS` (default 5) to each
  gap so network jitter cannot cause a false pacing violation.
- Keep `RD_TIME_SCALE` at 0.1 or above; below that, HTTP overhead is a large share of each gap.

## 3. Identity

- **Query key:** `query_key(query)`, the prototype's rule (lowercase, alphanumeric words, no
  duplicates, sorted). The cache, the merge table and the provider all use the key, never raw text.
- **`job_id`:** a string. The harness passes the workload's id; otherwise the API makes one. A
  duplicate `job_id` gets 409.
- **`trace_id`:** equals `job_id` for jobs; `POST /search` makes a fresh one per call.
- **`worker_id`:** `{hostname}-{pid}`.
- **`user`:** a handle matching `[a-z0-9-]{1,32}` (`USER_PATTERN`), taken from the MCP address
  `/mcp/u/{user}`; `anon` when absent. It is **not a login**: anyone can claim any handle. It exists
  so the gateway can give each person a fair share and the control room can show who is calling.
  The harness uses `anon` unless a fairness test sets users.
- **`client`:** one of `harness`, `claude`, `test`, on every request and event. Measured results
  come only from `harness`.
- **`run_id`:** one id per experiment run (or `dev`), on every request, event and metric, so runs
  can be filtered and the provider's counters reset per run.

## 4. Provider simulator (Satyaa)

`POST /search` takes `ProviderSearchRequest` and returns `ProviderSearchResult`.

- `ProviderSearchRequest`: `key`, `request_id`, `client`, `run_id`, `trace_id`
- `ProviderSearchResult`: `key`, `paper_ids`, `corpus_version`, `started_at_ms`, `finished_at_ms`

Rules:
- **It never refuses for rate limits.** It serves every call and counts overlap violations (a call
  starts while another is in flight) and pacing violations (two starts closer than `RD_PACING_MS`),
  like the prototype's `Backend`. **The counts must be 0 in every run; non-zero is a bug.** To test
  the alarm, send two direct calls back to back with `client` `test`: that must count one violation.
- **Results:** the prototype's `search()` over `RD_CORPUS_SIZE` papers. At corpus version 0 the
  ranking is exactly the prototype's (hash of `key|paper_id`); from version 1 on, the version joins
  the hash (`key|version|paper_id`), so results change after a bump. The version increases by 1
  every `RD_CORPUS_VERSION_EVERY_MS` (0 = never).
- **The provider owns `rd:corpus_version`** (§8). It writes the key at start-up, on every bump from a
  timer (not only when a call arrives), and on `POST /reset`; no other service writes it. Services
  that judge staleness read this key, so it never lags behind the provider while calls are served
  from the cache.
- **Latency:** `RD_PROVIDER_LATENCY_MS` × (1 + u), with u uniform in ±`RD_PROVIDER_LATENCY_JITTER`,
  drawn from a generator seeded with `RD_SEED`; then times the fault plan's `slowdown`.

`POST /faults` takes `FaultPlan`; the plan applies to every call until it is replaced, and `{}`
clears it. An injected error returns 500 `{"error": "injected_fault"}`. `GET /stats?run_id=...`
returns `ProviderStats` for that run. `POST /reset` with `{"run_id": ...}` zeroes that run's counters.

- `FaultPlan`: `slowdown`, `error_rate`, `pause_windows_ms`
- `ProviderStats`: `run_id`, `calls`, `overlap_violations`, `pacing_violations`, `corpus_version`

## 5. Gateway (Satyaa)

`POST /dispatch` takes `DispatchRequest` and **holds the HTTP request open** until the result or a
drop. Callers set their HTTP timeout above `deadline_ms` (converted to real time).

- `DispatchRequest`: `key`, `deadline_ms`, `client`, `run_id`, `trace_id`, `attempt`, `job_id`, `subagent_id`, `user`
- `DispatchResult`: `status`, `key`, `paper_ids`, `queue_wait_ms`, `provider_ms`, `corpus_version`, `reason`, `request_id`

Replies: 200 with `status` `ok`, or `status` `dropped` with a `reason`: 429 for `user_quota`, 503 for the rest:

| Reason | When |
|---|---|
| `queue_full` | The bounded queue holds `RD_QUEUE_MAX` requests |
| `deadline_unmeetable` | Before dispatch, remaining time is less than the p95 latency estimate. **No provider call is made and no pacing slot is used** |
| `retry_budget_exhausted` | The provider failed and the request used its `RD_RETRY_BUDGET` retries |
| `admission_rejected` | Used by the API when `POST /admit` says no |
| `provider_error` | The provider failed and the deadline leaves no time to retry |
| `user_quota` | The request's `user` is over `RD_USER_CALLS_PER_MIN` or `RD_USER_QUEUE_MAX` (reply 429, not 503) |

- One call in flight at a time; call starts at least `RD_PACING_MS` apart.
- Queue order is `RD_QUEUE_POLICY`: `fifo`, `round_robin` (one request per job in turn), or
  `fair_user` (one request per `user` in turn; the setting for the public service).
- **Per-user quotas:** with `RD_USER_CALLS_PER_MIN` above 0, a user's provider calls in any rolling
  simulated minute never exceed it; with `RD_USER_QUEUE_MAX` above 0, a user never holds more queued
  requests than that. Either limit drops the request with `user_quota`. Both default to 0 (no cap),
  so experiments are not distorted; the public deployment sets them (for example 8 and 10).
- **p95 latency estimate:** the nearest-rank 95th percentile of the last 100 provider latencies
  (simulated ms); `RD_PROVIDER_LATENCY_MS` until there is a first sample.
- **Retry backoff:** wait a uniform random time between 0 and min(`RD_PACING_MS` × 2^attempt,
  4 × `RD_PACING_MS`), then queue the request again; a retry still obeys pacing.
- **Request ids:** the gateway gives every provider attempt (retries included) a fresh `request_id`
  and returns the id of the attempt that succeeded in `DispatchResult.request_id` (`null` when
  dropped). The runner stores it with the result, which is how §12 finds the calls that were used.

`POST /admit` takes `AdmitRequest` and returns `AdmitResult` (always 200):

- `AdmitRequest`: `job_id`, `n_subagents`, `k`, `deadline_ms`, `expected_hit_rate`, `user`
- `AdmitResult`: `admitted`, `estimated_ms`, `reason`

Estimate: calls = `n_subagents × k × (1 − expected_hit_rate)`; time = (calls + current queue depth)
× `RD_PACING_MS`. Reject when time exceeds `deadline_ms`, or when the job alone needs more calls
than its user's `RD_USER_CALLS_PER_MIN` allows before the deadline (reason `user_quota`).

## 6. Job API (Muskan)

`POST /jobs` takes `JobRequest` and replies 202 with `JobAccepted` (`status` `admitted` or
`rejected`; a rejected job is final at once).

- `JobRequest`: `question`, `deadline_ms`, `client`, `run_id`, `plan`, `job_id`, `gather`, `user`
- `SubagentPlan`: `subagent_id`, `queries`
- `JobAccepted`: `job_id`, `trace_id`, `status`

Flow, in order:
1. If `plan` is missing, call `lead.plan` (experiments always send the workload's plan; the demo
   sends Claude's). Given or built, the plan costs the lead `RD_PLAN_MS` of thinking (a wait of
   `to_real_ms(RD_PLAN_MS)`). The job's `deadline_at_ms` is set when the request arrives, so planning
   time counts against the deadline.
2. Unless `RD_ADMISSION=off`, call `POST /admit` with `n_subagents` = plan length, `k` = the longest
   query list, `expected_hit_rate` = 0 (conservative), and `deadline_ms` = what is left after step 1.
3. Write the job hash, then one task per `SubagentPlan` on `rd:tasks`.
4. Start `lead.gather` for the job in a background thread. It follows `gather` (default
   `RD_GATHER_POLICY`): `wait_all` waits for every subagent; `deadline_partial` stops at the deadline
   minus `RD_GATHER_MARGIN_MS` and keeps what has finished. When it stops, it spends `RD_SYNTH_MS`
   writing the brief (a wait of `to_real_ms(RD_SYNTH_MS)`) and then sets the final status.
   `RD_SYNTH_MS` never exceeds `RD_GATHER_MARGIN_MS`, so `deadline_partial` is never late.

`GET /jobs/{job_id}` returns `JobView`; unknown id → 404.

- `JobView`: `job_id`, `status`, `completeness`, `n_subagents`, `subagents`, `created_at_ms`, `finished_at_ms`
- `SubagentView`: `subagent_id`, `status`, `steps_done`, `k`, `paper_ids`, `stale_steps`

- Job `status`: `admitted`, `running`, then one final value: `on_time`, `late`, `expired`,
  `rejected`, `failed`. Task status: `queued`, `running`, `done`, `failed`.
- **The brief** is the `subagents` list of a final `JobView`. `completeness` = subagents with status
  `done` ÷ `n_subagents`. A dropped search (any reason) ends only its own subagent `failed`.
- **Final status**, set by `lead.gather` when it stops (the API sets `rejected` at admission):
  1. completeness 0 and every subagent `failed` → `failed`;
  2. otherwise completeness 0 → `expired`;
  3. otherwise the brief was written by the deadline → `on_time`, else `late` (only `wait_all`
     can be late; `deadline_partial` stops in time).
- **A brief is correct** when it is `on_time` (so completeness is above 0) and no included subagent
  has `stale_steps` above 0.
- `GET /jobs/{job_id}/trace` returns that job's events in order (from `rd:events`).

`POST /search` (one search, used by Mode B) takes `SearchRequest`, calls `runner.search_once`, and
returns `SearchResult`: 200 if `ok`, 503 if `dropped`. `source` is `cache`, `merged` or `provider`.

- `SearchRequest`: `query`, `deadline_ms`, `client`, `run_id`, `user`
- `SearchResult`: `status`, `key`, `paper_ids`, `latency_ms`, `source`, `corpus_version`, `reason`

Invalid input anywhere → 400 (map your framework's default validation code to 400).

## 7. MCP tools (Satyaa)

**A public service.** The server runs over `streamable-http` on the AWS stack, and a Cloudflare
quick tunnel on that instance gives it a public `https://` address. Anyone's Claude can add it:

- **Claude Desktop or claude.ai:** Settings → Connectors → Add custom connector, with the URL
  `https://TUNNEL-HOST/mcp/u/HANDLE` (the MCP docs: the URL needs `https://` and may carry path
  components).
- **Claude Code** (terminal, or the Desktop app's Code tab):
  `claude mcp add --transport http researchdesk https://TUNNEL-HOST/mcp/u/HANDLE`.

Rules for the public server:
- `POST /mcp/u/{user}` sets `user` on every call it makes; `POST /mcp` uses `anon`. A handle that
  does not match `USER_PATTERN` gets 400.
- It accepts the tunnel hostname from `RD_PUBLIC_HOST` besides localhost (the SDK otherwise answers
  only localhost, as a guard against DNS rebinding).
- It answers with plain JSON, not a stream, because Cloudflare quick tunnels do not support
  Server-Sent Events. (Both points come from the LeaseBoston build, `~/Projects/LeaseBoston/README.md`.)
- The quick-tunnel URL changes every time the tunnel restarts; post the current one in the team chat.
- **No login** (decided 2026-11-22): per-user quotas protect the shared budget, but a handle is not
  proof of identity. OAuth 2.1, the MCP-standard sign-in, is future work.

`stdio` (`MCP_TRANSPORTS`) stays for local development only: a Desktop on the same Mac can launch
the server from `claude_desktop_config.json`, with `RD_API_URL=http://localhost:8000`.

The server only calls the Job API; it holds no state. Every call it makes uses `client` `claude`,
the caller's `user`, and the run id from `RD_RUN_ID`.

| Tool | Inputs | Calls |
|---|---|---|
| `start_research` | `question`, `deadline_s`, `plan` (optional list of query lists, one per subagent) | `POST /jobs` |
| `get_research` | `job_id` | `GET /jobs/{job_id}` |
| `search_papers` | `query`, `deadline_s` | `POST /search` |

Tools take seconds (friendlier for Claude) and convert to `deadline_ms`. **The measured system never
depends on MCP:** the harness calls the Job API directly.

**Optional progress card (MCP App, task T12b).** `start_research` and `get_research` may attach the
UI resource `ui://researchdesk/progress.html` (`MCP_UI_RESOURCE`). In a host that draws MCP Apps, the
card shows one progress bar per subagent and calls `get_research` every few seconds until the job is
final. Hosts without MCP Apps get the same data as text, so the tools never depend on the card.

## 8. Redis keys and streams (Sruthilaya; leases by Satyaa)

| Key | Type | Holds | Written by |
|---|---|---|---|
| `rd:cache:{qkey}` | string, TTL `RD_CACHE_TTL_MS` | JSON `{"paper_ids": [...], "corpus_version": n, "request_id": "..."}` (`request_id` from `DispatchResult`) | runner, after a provider result |
| `rd:inflight:{qkey}` | string, `SET NX PX` `RD_INFLIGHT_LEASE_MS` | owner token `worker_id:uuid` | the claimant of a search |
| `rd:waiters:{qkey}` | sorted set | member = waiter id (`{worker_id}:{job_id}:{subagent_id}:{step}`, or `api:{trace_id}` for `POST /search`), score = waiter's `deadline_at_ms` | each merged waiter |
| `rd:done:{qkey}` | pub/sub channel | JSON `{"status": "ok"}` once the result is in the cache, or `{"status": "dropped", "reason": ...}` | the claimant |
| `rd:corpus_version` | string | current corpus version (§4) | provider |
| `rd:job:{job_id}` | hash | `status`, `n_subagents`, `done`, `failed`, `completeness`, `created_at_ms`, `finished_at_ms`, `deadline_at_ms`, `gather`, `client`, `user`, `run_id` | API, lead |
| `rd:job:{job_id}:sub:{subagent_id}` | hash | `status`, `steps_done`, `k`, `stale_steps`, `worker_id` | runner |
| `rd:ckpt:{job_id}:{subagent_id}:{step}` | string, `SET NX` | JSON `{"paper_ids": [...], "corpus_version": n, "source": "cache", "stale": false, "request_id": "..."}` (`source` as in §6; `request_id` is the provider call that produced the result, also for cache hits and merged waiters); first write wins, so writes are idempotent. `JobView.paper_ids` is built from these in step order | runner |
| `rd:hb:{worker_id}` | string, `PX` `RD_LEASE_MS` | last heartbeat | `lease.heartbeat` |
| `rd:metrics:{run_id}` | hash | worker-side counters (§11) | `events.count` |
| `rd:tasks` | stream, consumer group `workers` | one entry per subagent task | API |
| `rd:events` | stream, `MAXLEN ~ 100000` | field `data` = one `EventRecord` JSON | `events.emit` |

`rd:tasks` entry fields: `job_id`, `subagent_id`, `queries` (JSON list), `deadline_at_ms`,
`trace_id`, `client`, `user`, `run_id`, `attempt`.

**Merge protocol.** A runner with a cache miss tries `SET rd:inflight:{qkey} NX PX`. If it wins, it
dispatches with `deadline_ms` = the latest deadline in `rd:waiters:{qkey}` (its own included),
converted with `to_sim_ms(latest deadline_at_ms - Redis now, RD_TIME_SCALE)`. That deadline is fixed
when the dispatch starts: a waiter that arrives later with a later deadline cannot extend it, and if
the dispatch is dropped that waiter claims again, which costs one more provider call (visible as an
extra `search.claimed` event). **While the dispatch is open it renews the claim** every `RD_INFLIGHT_LEASE_MS` ÷ 3, but only while
the key still holds its own token, so a long gateway queue never lets the claim lapse. On a result it
writes the cache, publishes `{"status": "ok"}` on `rd:done:{qkey}` and deletes the claim; on a drop it
publishes `{"status": "dropped", ...}` and deletes the claim. A runner that loses the claim adds
itself to `rd:waiters:{qkey}` and waits for the message, also polling the cache and the claim key
(pub/sub can lose messages). On `dropped`, or when the claim key is gone with no cache entry, a waiter
whose deadline is still ahead claims the key again; one whose deadline has passed ends its subagent
`failed`. A waiter removes its own member from `rd:waiters:{qkey}` when it stops waiting (result,
expiry or claiming again), and the claimant deletes the set when it releases the claim, so a stale
waiter never raises the dispatch deadline. With `RD_REUSE_MODE` `none` nothing is cached; with `cache`, no merging.
**Stale:** a cache hit whose `corpus_version` is below `rd:corpus_version` is served but counted in
`stale_steps`.

**Leases.** Each worker reads `rd:tasks` as consumer `worker_id` in group `workers`. A task is
acknowledged only when it is done. **Liveness comes from the heartbeat key, not from stream idle
time:** a long subagent (k steps of `RD_THINK_MS` plus queueing) is idle on the stream for longer
than `RD_LEASE_MS` while it is healthy. With `RD_LEASES=on`, another worker may reclaim a pending task
only when its owner's `rd:hb:{worker_id}` key has expired. It then resumes at `runner.resume_step`,
and `claim` sets the returned `attempt` field to the entry's delivery count minus 1 (stream entries
cannot be edited; check the Redis docs for the pending-entry commands). With `RD_LEASES=off`, nothing is reclaimed: a crashed worker's task stays
pending and its subagent never finishes (the E4 baseline).

### In-process Python interfaces (cross-lane calls)

Plain synchronous functions. Each module opens its own Redis and HTTP clients from the `Settings`
it is given. An async caller (the Job API) runs them in a worker thread.

| Function | Owner | Called by | Does |
|---|---|---|---|
| `researchdesk.workflow.runner.search_once(settings, query, deadline_ms, client, run_id, trace_id, job_id=None, subagent_id=None, user="anon") -> SearchResult` | Sruthilaya | runner, Job API `POST /search` | One search: cache → merge → `POST /dispatch` (with `user`, so the gateway's per-user quotas apply); the only emitter of `search.*` events |
| `researchdesk.workflow.runner.run_subagent(settings, task, worker_id) -> str` | Sruthilaya | worker | Runs one `rd:tasks` entry (`task` = its fields) from `resume_step` to the end; returns a task status value |
| `researchdesk.workflow.runner.resume_step(settings, job_id, subagent_id) -> int` | Sruthilaya | runner, lease code | First step with no checkpoint |
| `researchdesk.workflow.lead.plan(settings, question) -> list[SubagentPlan]` | Sruthilaya | Job API | Fallback plan when `JobRequest.plan` is missing |
| `researchdesk.workflow.lead.gather(settings, job_id) -> JobView` | Sruthilaya | Job API, one background thread per job | Waits per the gather policy, writes the final status and completeness |
| `researchdesk.workflow.lease.claim(settings, worker_id) -> Optional[tuple[str, dict]]` | Satyaa | worker | Next task (new, or reclaimed when `RD_LEASES=on`): stream entry id and fields |
| `researchdesk.workflow.lease.heartbeat(settings, worker_id, entry_id) -> None` | Satyaa | worker, every `RD_HEARTBEAT_MS` | Keeps the lease; writes `rd:hb:{worker_id}` |
| `researchdesk.workflow.lease.ack(settings, entry_id) -> None` | Satyaa | worker, after `run_subagent` | Marks the task done |
| `researchdesk.metrics.events.emit(settings, record) -> None` | Muskan | every service | Writes one `EventRecord` to the log and to `rd:events` |
| `researchdesk.metrics.events.count(settings, metric, labels, amount=1) -> None` | Muskan | worker-side code | Adds to a counter in `rd:metrics:{run_id}` |

## 9. Events and logs (Muskan; every service emits)

Every state change is one `EventRecord`, written by `events.emit` two ways: one JSON line in the
service's log, and `XADD rd:events MAXLEN ~ 100000 * data JSON`. Until `emit` lands (M7a), print the
JSON line only. The live control room, `GET /jobs/{job_id}/trace` and the harness read the stream.

- `EventRecord`: `ts_ms`, `run_id`, `client`, `service`, `event`, `trace_id`, `job_id`, `subagent_id`, `step`, `worker_id`, `key`, `fields`, `user`

## 10. Event names

| Event | Emitted by | Useful `fields` |
|---|---|---|
| `run.started` | harness | `setting`, `seed`, `n_jobs` |
| `run.finished` | harness | `csv_path` |
| `job.submitted` | api | `n_subagents`, `deadline_ms` |
| `job.admitted` | api | `estimated_ms` |
| `job.rejected` | api | `reason` |
| `job.planned` | api | `n_subagents`, `k` |
| `job.gathered` | lead | `policy`, `completeness` |
| `job.finished` | lead | `status`, `completeness`, `latency_ms` |
| `task.enqueued` | api | `queries` |
| `task.claimed` | worker | `attempt` |
| `task.step_done` | runner | `source`, `request_id` |
| `task.lease_expired` | lease code | `idle_ms` |
| `task.reclaimed` | lease code | `from_worker`, `resume_step` |
| `task.done` | runner | `steps` |
| `task.failed` | runner | `reason` |
| `search.cache_hit` | runner (`search_once`) | `corpus_version` |
| `search.merged` | runner (`search_once`) | `waiters` |
| `search.claimed` | runner (`search_once`) | `deadline_ms` |
| `search.stale` | runner (`search_once`) | `cached_version`, `current_version` |
| `search.done` | runner (`search_once`) | `source`, `latency_ms` |
| `gateway.queued` | gateway | `depth` |
| `gateway.sent` | gateway | `queue_wait_ms` |
| `gateway.dropped` | gateway | `reason` |
| `gateway.retry` | gateway | `attempt`, `backoff_ms` |
| `gateway.admission` | gateway | `admitted`, `estimated_ms` |
| `provider.served` | provider | `latency_ms`, `corpus_version` |
| `provider.violation` | provider | `kind` (`overlap` or `pacing`) |
| `provider.fault` | provider | `fault` |
| `worker.started` | worker | `pid` |
| `worker.heartbeat` | worker | at most one per `RD_HEARTBEAT_MS` |

E4's recovery time is measured from events: `task.lease_expired` to the `task.done` that follows
`task.reclaimed`.

## 11. Metrics

Every metric also carries the label `run_id`. **Worker-side counters** (owner "worker side") are
added with `events.count` into `rd:metrics:{run_id}`, because workers have no HTTP server; the Job
API exports that hash on its `GET /metrics`. The rest are served by their own service.

| Metric | Type | Labels | Owner |
|---|---|---|---|
| `rd_jobs_total` | counter | `status` | api |
| `rd_tasks_total` | counter | `status` | worker side |
| `rd_searches_total` | counter | `source` | worker side (`search_once`) |
| `rd_merge_waiters_total` | counter | — | worker side |
| `rd_stale_answers_total` | counter | — | worker side |
| `rd_gateway_queue_depth` | gauge | — | gateway |
| `rd_gateway_calls_total` | counter | — | gateway |
| `rd_gateway_drops_total` | counter | `reason` | gateway |
| `rd_gateway_retries_total` | counter | — | gateway |
| `rd_admission_total` | counter | `decision` | gateway |
| `rd_provider_calls_total` | counter | — | provider |
| `rd_provider_violations_total` | counter | `kind` | provider |
| `rd_lease_expiries_total` | counter | — | worker side (lease code) |

Job latency is not a Prometheus metric: it is in each `job.finished` event (`latency_ms`) and in the
harness CSV (`p95_latency_s`).

## 12. Workload file and results

`prototype/workload.py` writes a `WorkloadFile`; `harness/` replays it, so the simulator and the
deployed system run the same jobs.

- `WorkloadFile`: `version`, `seed`, `params`, `jobs`
- `WorkloadJob`: `job_id`, `arrival_s`, `deadline_s`, `plan`

Times are simulated seconds. **`deadline_s` is relative to arrival** (the prototype's `Question`
stores an absolute deadline: convert with `deadline - arrival`). The harness posts each job at
`arrival_s` × 1000 × `RD_TIME_SCALE` real ms after the run starts, with `deadline_ms` =
`deadline_s` × 1000.

Harness CSV columns, in order: `run_id`, `setting`, `seed`, `briefs_per_min`,
`complete_briefs_per_min`, `on_time_correct`, `wrong_briefs`, `late`, `expired`, `rejected`,
`failed`, `upstream_calls`, `calls_per_brief`, `p95_latency_s`, `completeness_mean`, `cache_hits`,
`merged`, `wasted_calls`, `max_queue_depth`, `violations`. Times in the CSV are simulated.

- Columns the prototype's `summarize` already has keep its definitions, except `wasted_calls`
  (next bullet). The simulator (S3) and the harness (M6) both produce **all** of these columns, so
  their CSVs compare row for row.
- **`wasted_calls`** = `upstream_calls` minus the number of distinct provider calls that were used. A
  call is used when its `request_id` appears in a `task.step_done` event of a step that belongs to
  an on-time correct brief. A call whose result served several steps (cache hits, merged waiters)
  counts once; a failed or retried attempt is never used. The harness computes it from `rd:events`.
  (With one subagent and no reuse this equals the prototype's calls − k × on-time correct briefs.)
- `briefs_per_min` counts correct briefs (§6), partial ones included (completeness above 0);
  `complete_briefs_per_min` counts only correct briefs with completeness 1. Both are always written,
  and E3 reports both: a gather policy that returns partial briefs would otherwise win on the first
  column alone. With one subagent per job the two are equal.
- `setting` is a free-text label from the experiment runner, such as `workers=4,rate=12,admission=on`.
- `rejected` counts jobs refused at admission; `failed` and `expired` follow the §6 final-status
  rules. In the prototype's one-subagent baseline, a question whose search was dropped for a full
  queue was called `rejected`; under §6 it is `failed`, and S3 renames it.
- The harness reads `upstream_calls` and `violations` from the provider's `GET /stats` for its run,
  and computes `cache_hits`, `merged` and `max_queue_depth` from its run's events in `rd:events`.
- **Simulator vs deployed:** a deployed result "agrees" when its median `briefs_per_min` is within
  15% of the simulator's for the same workload (proposed; the team confirms).

## 13. Settings (environment variables)

One `config/.env` file for Compose; `Settings.from_env(os.environ)` reads them.

| Variable | Default | Meaning |
|---|---|---|
| `RD_TIME_SCALE` | 1.0 | real ms per simulated ms |
| `RD_PACING_MS` | 3000 | minimum gap between provider call starts |
| `RD_PACING_SAFETY_REAL_MS` | 5 | the gateway's extra gap, **real** ms |
| `RD_PROVIDER_LATENCY_MS` | 1000 | provider latency |
| `RD_PROVIDER_LATENCY_JITTER` | 0.0 | ± fraction of uniform jitter; 0 = fixed, as in the prototype |
| `RD_CORPUS_SIZE` | 200 | papers in the synthetic corpus |
| `RD_CORPUS_VERSION_EVERY_MS` | 0 | corpus version bump interval; 0 = never |
| `RD_QUEUE_MAX` | 50 | gateway queue bound |
| `RD_QUEUE_POLICY` | fifo | `fifo`, `round_robin` or `fair_user` |
| `RD_ADMISSION` | on | `on` or `off` |
| `RD_RETRY_BUDGET` | 2 | retries per request after a provider error |
| `RD_USER_CALLS_PER_MIN` | 0 | per-user cap on provider calls in a rolling simulated minute; 0 = no cap |
| `RD_USER_QUEUE_MAX` | 0 | per-user cap on queued gateway requests; 0 = no cap |
| `RD_LEASES` | on | `off`: never reclaim a crashed worker's task (E4 baseline) |
| `RD_LEASE_MS` | 10000 | task lease length |
| `RD_HEARTBEAT_MS` | 3000 | worker heartbeat interval |
| `RD_INFLIGHT_LEASE_MS` | 15000 | in-flight claim expiry |
| `RD_CACHE_TTL_MS` | 600000 | cache entry lifetime |
| `RD_REUSE_MODE` | cache_merge | `none`, `cache` or `cache_merge` |
| `RD_GATHER_POLICY` | deadline_partial | `wait_all` or `deadline_partial` |
| `RD_GATHER_MARGIN_MS` | 5000 | time kept for writing the brief |
| `RD_THINK_MS` | 8000 | simulated agent thinking after each result |
| `RD_PLAN_MS` | 2000 | simulated time the lead spends planning before it fans out (§6) |
| `RD_SYNTH_MS` | 4000 | simulated time the lead spends writing the brief; at most `RD_GATHER_MARGIN_MS` (§6) |
| `RD_SEED` | 0 | seed for latency jitter and faults |
| `RD_RUN_ID` | dev | run id |
| `RD_REDIS_URL` | redis://redis:6379/0 | Redis |
| `RD_PROVIDER_URL` | http://provider:8001 | provider |
| `RD_GATEWAY_URL` | http://gateway:8002 | gateway |
| `RD_API_URL` | http://api:8000 | Job API |
| `RD_PUBLIC_HOST` | (empty) | the tunnel hostname the MCP server accepts besides localhost; empty = localhost only |

## 14. HTTP status codes

200 ok · 202 accepted (`POST /jobs`) · 400 bad request · 404 unknown job · 409 duplicate `job_id` ·
429 dropped for `user_quota` · 500 injected provider fault · 503 dropped for any other reason (the body
carries `reason`).

## 15. Left to the owners

Framework choices inside a service, the Prometheus client, how the board streams to the browser,
and the exact lease mechanism, as long as the names and behaviour above hold. Check each library's
own docs; nothing here assumes a library's API.
