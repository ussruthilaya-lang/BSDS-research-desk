# Handoff: Muskan

**Lane:** the Job API, the worker process, Docker Compose, the replay harness, observability
(events, Prometheus, Grafana), the **live control room**, and the AWS scripts. **Leads E1**
(throughput ceiling and admission control) and the **simulator-vs-real check**.

Read `CLAUDE.md` (shared rules) and all of `docs/contracts.md`. §4 and §5 matter for the harness and
for admission; §8 to §12 are mostly yours.

## What you produce for the others

| Thing | Contract section | Used by |
|---|---|---|
| Event helper `src/researchdesk/metrics/events.py`: **`emit`** and **`count`**, by **Wed 11/25** | §8 interfaces, §9 | every service and the runner |
| Job API (port 8000) per §6, including `POST /search` and `GET /metrics` exporting `rd:metrics:{run_id}` | §6, §11 | the harness (you), Satyaa's MCP server (T12) |
| Worker process: `lease.claim` → `runner.run_subagent` → `lease.ack`, with `lease.heartbeat` every `RD_HEARTBEAT_MS`; `worker_id` = `{hostname}-{pid}` | §3, §8 | E2, E4 |
| `docker-compose.yml` and `config/.env` running every §1 service: redis, provider, gateway, mcp, api, worker, board, prometheus, grafana | §1, §13 | everyone's integration tests and experiments |
| Skeletons by **Wed 11/25**: api and board answer only `GET /health`; the worker starts, emits `worker.started` and idles | §1 | Compose |
| Replay harness writing the §12 CSV | §12 | E1 (you), E2 (Sruthilaya), E4 (Satyaa) |
| Prometheus config, the Grafana dashboard JSON, and a script that prints one job's timeline from its `trace_id` | §9, §11 | everyone |
| Live control room (port 8004) | §9, §10 | the demo, debugging, the report's screenshots |
| AWS bring-up and teardown scripts | — | every AWS run |
| Events `run.*`, `job.submitted`, `job.admitted`, `job.rejected`, `job.planned`, `task.enqueued`, `task.claimed`, `worker.*`; metric `rd_jobs_total` | §10, §11 | the live control room |

## What you need from the others

| Thing | From | Target | Until it lands |
|---|---|---|---|
| Skeletons for provider, gateway, mcp | Satyaa (T4, T5, T12) | Wed 11/25 | none needed: they are due before Compose |
| Provider and gateway services | Satyaa (T4, T5) | Fri 11/27, Sun 11/29 | the skeletons |
| `POST /admit` | Satyaa (T6) | Wed 12/2 | `RD_ADMISSION=off` |
| `runner.run_subagent`, `runner.search_once`, `lead.plan`, `lead.gather` | Sruthilaya (S7, S8) | Thu 12/3, Sat 12/5 | a stub runner that calls `POST /dispatch` with no cache; a stub gather that waits for every subagent |
| `lease.claim`, `lease.heartbeat`, `lease.ack` | Satyaa (T7) | Sat 12/5 | a plain consumer group without reclaim |
| `WorkloadFile` JSON from the job model | Sruthilaya (S2) | Wed 11/25 | a tiny hand-written workload file |

## Your tasks, in order

| ID | Task | Files | Target | Done when |
|---|---|---|---|---|
| M0 | HW9 section 3 (objectives), section 7 (impact; offer classmates the harness to load-test it), and sections 8 to 10 from the team call | shared draft | **Sun 11/22, 11:59 pm** | Sections in the draft |
| M2 | Review contract §6 and §9 to §13; approve the PR | `docs/contracts.md` | Tue 11/24 | PR merged with all three approvals |
| M1 | Repo hygiene: a `dev` extra with pytest in `pyproject.toml`; a GitHub Actions workflow running pytest on every PR; a GitHub Project board with one issue per task ID | `pyproject.toml`, `.github/workflows/` | Tue 11/24 | CI green on a test PR; the board lists every S, T and M task |
| M7a | Event helper: `emit` (log line plus `XADD` to `rd:events`) and `count` (adds to `rd:metrics:{run_id}`) per §8 and §9 | `src/researchdesk/metrics/events.py` | Wed 11/25 | A test against a real or fake Redis shows one `rd:events` entry whose `data` field parses with `EventRecord.from_json`, and the counter in `rd:metrics:{run_id}` goes up by the amount given |
| M5 | Docker Compose with one `config/.env`; health checks on every service | `docker-compose.yml`, `config/` | Fri 11/27 | `docker compose up` starts every service; every HTTP health check passes and the worker containers stay up |
| M3 | Job API per §6, in the §6 flow order (plan → admit → job hash → tasks → gather thread), carrying `user` into the job hash, tasks and events; `POST /search` calls `search_once`; `GET /metrics` | `src/researchdesk/api/` | Sun 11/29 | A curl `POST /jobs` returns a job id and `GET /jobs/{job_id}` shows its status changing; `POST /search` returns a `SearchResult` |
| M4 | Worker process; `docker compose up --scale worker=N` | `src/researchdesk/workflow/worker.py` | Wed 12/2 | One job end to end with the stub runner and no reuse; repeated with the real runner once S7 lands |
| M6 | Replay harness: posts each job at its scaled arrival time, writes the §12 CSV; `upstream_calls` and `violations` from the provider's `GET /stats`; `cache_hits`, `merged`, `max_queue_depth` from the run's events; correctness per §6 | `harness/` | Wed 12/2 | The base-case workload (`docs/handoff/README.md`) runs on Compose and writes a CSV with every §12 column |
| M7 | Prometheus scraping every service at a few seconds, the Grafana dashboard JSON, the timeline script | `config/prometheus.yml`, `config/grafana/`, `src/researchdesk/metrics/` | Sat 12/5 | Dashboard screenshot during a run; a timeline printed for one job |
| M12 | **Live control room** (see below) | `src/researchdesk/board/` | Sat 12/5 | During a Compose run the page shows each event as it arrives; killing a worker shows `task.lease_expired` then `task.reclaimed`; two direct back-to-back provider calls with `client` `test` produce a `provider.violation` and turn the strip red |
| M8 | AWS bring-up and teardown: EC2 only (no NAT gateway, load balancer, ElastiCache or RDS); the provider on its own instance; on the instance with the MCP server, start a Cloudflare quick tunnel and print its public URL; set `RD_USER_CALLS_PER_MIN`, `RD_USER_QUEUE_MAX` and `RD_QUEUE_POLICY=fair_user` for the public service; log the credit balance before and after each session | `deploy/` | Sat 12/5 | The stack is up from nothing in under 15 minutes and down with one command; the script prints the tunnel URL and a Claude Desktop custom connector reaches it; balance logged |
| M9 | **E1** with the job model and admission control: simulator sweep, then 3 points on Compose and AWS; the simulator-vs-real check on the base-case workload | `experiments/e1/` | Sun 12/6 | CSV and figure; a table of simulator vs deployed briefs per minute with the percentage difference per point; any point more than 15% off (proposed tolerance) has a measured cause in the report |
| M11 | Report sections for the architecture, observability, E1 and the simulator-vs-real check; poster layout | `docs/` | Wed 12/9 | In the shared draft |

M10 (the old demo page) is dropped: the demo is Claude over the MCP server (Satyaa, T12 and T13).

## M12: the live control room

One page (port 8004) that **only displays** events from `rd:events`; it never changes state.

| Panel | Shows live |
|---|---|
| Status strip | provider violations (red if above 0), gateway queue depth, provider calls per minute against 20, cache hit rate, jobs running and finished |
| Job board | one row per job: a progress bar per subagent; each search marked cache hit, merged, queued, sent or dropped; time left to the deadline; completeness |
| Gateway timeline | the last 60 s of provider call starts on the `RD_PACING_MS` grid |
| Workers and leases | each worker's current task and last heartbeat; lease expiries and reclaims |
| Users | one row per `user`: calls in the last minute against its quota, `user_quota` drops, jobs running |
| Event feed | the raw events, filterable by `client`, `user` and `run_id` |
| Run progress | from `run.started` and `run.finished`: setting, seed, jobs posted |

Mode B shows up by itself: its calls carry `client` = `claude`. How the page streams to the browser
is your choice; check the framework's docs.

## Watch-outs

- Prometheus scrapes every 1 minute by default and Grafana refreshes no faster than every 5 seconds
  by default (both from their docs). Set a scrape interval of a few seconds for experiments; the
  live control room covers per-job progress.
- Harness times: post at `arrival_s` × 1000 × `RD_TIME_SCALE` real ms after the start; send
  `deadline_ms` = `deadline_s` × 1000; report CSV times in simulated units.
- Reset the provider's counters per run (`POST /reset`).
- Never mix a Mode B demo into a measured run.

## Start here

1. Tonight: HW9 sections 3, 7 and 8 to 10 (M0) after the team call.
2. Review the contract (M2), then M7a (others need `emit` early), M1, and the Compose skeleton (M5).
3. M3 with a stub runner, then M6 with a hand-written workload file.
