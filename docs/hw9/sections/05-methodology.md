# 5. Methodology

**5a. Methods and approach.** Research Desk is designed as six small services: the job API, workers, gateway, provider simulator, MCP server and live control room. They share one Redis store (a fast in-memory database). The same code is meant to run on a laptop with Docker Compose and on a few AWS EC2 machines. The diagram shows the planned parts. Most services are still to be built, and the Feasibility paragraph says what exists today.

![Architecture diagram of Research Desk. The replay harness (green) produces every measured result. The demo path (orange) goes through the MCP server. Every service reports to one event and metric pipeline.](figures/architecture.svg)

*Architecture diagram. The replay harness (green) produces every measured result. The demo path (orange) goes through a thin MCP server. Every service reports to one event and metric pipeline.*

*One job, step by step.*

1. **Submit and admit.** A client sends a question and a deadline to the job API. Admission control estimates the job's calls (N times k, less the expected cache hits), adds the calls already queued, and multiplies by the three-second gap. If this is longer than the deadline, it rejects the job at once. A rejected job spends no calls.
2. **Plan and fan out.** The lead turns the question into N subagent tasks of k searches each. It puts them on a Redis task stream. In experiments, the plan comes from a workload file. In the demo, Claude writes it.
3. **Search.** A free worker takes a task. For each step, it makes a normalised key from the query and checks the cache. A hit costs no provider call. If another worker is already fetching that key, the worker waits for that result. Otherwise it claims the key (the claim expires, and the worker renews it) and sends the search to the gateway.
4. **Gateway.** One gateway is the only caller of the provider. It keeps a bounded queue and drops a request whose deadline can no longer be met, judged against a 95th-percentile latency estimate. It starts calls at least three seconds apart with one call in flight, retries within a budget, and caps each user's share. The result goes into the cache and wakes every waiter.
5. **Checkpoint.** After each step, the worker saves the result under the job, subagent and step. Writing it twice is harmless.
6. **Gather and brief.** The lead either waits for every subagent, or stops at the deadline minus a margin and uses what has finished. The brief records its completeness, the share of subagents included.

*Failure handling.* A worker's lease is a heartbeat key that expires when the worker goes quiet. Another worker then takes the task and resumes after the last saved step. If the worker that holds a search's claim crashes, the claim expires and a waiter claims the search again. A merged search keeps the latest waiter's deadline. A dropped search fails only its own subagent.

*How AI is used.* Section 1b gives the role of AI. Measured runs replay scripted agents. Real Claude agents will appear in the demonstration only.

A thin MCP server will expose the backend as a live service over Streamable HTTP, behind a Cloudflare tunnel. A person will add its address as a custom connector in Claude Desktop, or with `claude mcp add` in Claude Code. A handle in the address will identify the caller for per-user quotas. There will be no login, so a handle is not proof of identity.

There are two demonstration modes. In one, Claude plans a question and starts a job through the MCP tools. In the other, several Claude subagents each call one search tool. Neither mode is part of a measured run.

*Observability.* Section 1b gives the overview. Every state change will be one structured event with a trace identifier, a run identifier, the client, the user, the job and the subagent. Events go to a log and to a Redis event stream.

- **Prometheus counters** will cover jobs, tasks, searches by source (cache, merged or provider), queue depth, calls and drops by reason, admission decisions, provider violations and lease expiries.
- **A Grafana dashboard** will show the counters over time. Prometheus scrapes once a minute and Grafana refreshes at most every 5 seconds by default (both from their documentation). Experiments set a scrape interval of a few seconds.
- **A live control room page** will show the event stream as it arrives: violations, queue depth, calls a minute against the limit of 20, cache hit rate, a progress bar for every subagent, worker leases and per-user usage.
- **The provider simulator is the correctness alarm.** It counts overlap and pacing violations. The count must be zero in every run.

*Feasibility.* A working prototype and the groundwork already exist:

- a discrete-event simulator and a seeded workload generator
- a paced gateway with a bounded queue and deadline checks
- a cache and in-flight merge, workers and metrics
- an Experiment 1 runner, a first Experiment 2 comparison and an automated test suite (Section 6)
- the shared contract, the event helper, and health-only skeletons of the job API, the live control room and the worker

The tests run on every pull request. These parts are still to be built, with targets on or before Sat 12/5: the gateway service, the provider service, the subagent runner, the task leases, the MCP server, the replay harness and the Docker Compose stack.

Full sweeps run on the simulator in seconds. The deployed system confirms a few points of each. Real-time pacing makes a deployed run slow, so every service shares a time-scale setting. A value of 0.1 turns the three-second gap into 0.3 seconds.

The scope is small on purpose. Agents are scripted, there is one gateway, and there is no consensus protocol. Tools are read-only, because searching is safe to cache and merge, and booking is not. AWS use is limited to EC2, and the Learner Lab credit is logged before and after each session.

**5b. Experiments and tradeoffs.** Every setting runs with three seeds. Results report the median and the range. Each experiment has two parts: the full sweep on the simulator, and two or three confirming points on the deployed system, which replays the same workload file. A deployed point that differs from the simulator by more than 15 percent gets a measured explanation.

The primary metric is correct, complete briefs finished on time per minute. The secondary metrics are:

- provider calls per brief, and wasted calls
- 95th-percentile job latency, and completeness
- cache and merge hit rates
- rejected, expired and failed jobs
- recovery time and duplicate calls after a crash

| # | Question | Sweep | Tradeoff evaluated |
|---|---|---|---|
| E1 | Where does throughput stop rising, and does admission control stop the collapse past that point? | workers {1, 2, 4}, arrival rate, admission {off, on}, no reuse | Accepting every job against rejecting early: fewer rejections against fewer wasted calls |
| E2 | How much do the cache and merging save, and when? | reuse {none, cache, cache plus merge}, subagents per job N {1, 3, 5, 10}, topic overlap within a job, skew across jobs | Memory and staleness against calls saved; waiting to merge against a duplicate call |
| E3 (simulator only) | Is a partial answer on time better than a complete answer late? | gather {wait for all, stop at the deadline}, provider slowdown {none, 2 times, 5 times} | Completeness against on-time rate |
| E4 | Does a crashed worker cost the job? | kill a worker mid-subagent; leases {off, on}; lease lengths 5, 10 and 20 seconds | Lease length: fast recovery against false takeovers that cause duplicate calls |

Experiments on fairness between wide and narrow jobs and on failover of the gateway are future work and are not promised. Section 6 gives the workloads and what has been measured so far.
