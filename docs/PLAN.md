# Research Desk: Project Plan

Status: draft v1 (2026-11-20). Open decisions are listed at the end.

## 1. Summary
Research Desk is a **budget-aware gateway for agent tool calls**. Many agents share one rate-limited tool backend. Each task fans out into several sequential calls, agents retry on errors, and many ask identical things. The gateway shares results (cache), merges identical in-flight calls, and schedules the rest under a fixed budget with deadlines, so more tasks finish on time and human users are not crowded out.

- **Scope rule:** read-only tools only. Calls with side effects (booking, sending) are out of scope, because caching or merging them is unsafe. Write-path contention is a different problem (see RegRush).
- **Backend:** simulated, with arXiv-like limits (1 in flight, 3 s pacing, at most 20 calls/min), a fixed synthetic corpus, and fault injection.
- **Agents:** scripted, for reproducibility. Real LLM agents are future work.
- **Headline scenario:** a multi-step support-style flow (customer, order, status, policy, answer) where one slow or stale step affects the rest. Paper search is the first implemented tool.

## 2. Stakeholders
- Operators deploying agents, who want more tasks done under the same budget.
- Human users sharing the backend, who should not be starved.
- Tool and API providers, who get fewer duplicate and retry-storm requests.

## 3. Architecture
Workers run agent scripts. Shared state (Redis) holds the result cache and the in-flight table. A single gateway owns the bounded queue, the pacer and the dispatch to the backend. Metrics events are emitted at every step.

```
 Replay harness (agents, humans) -> Workflow API -> Workers 1..N
                                                      |       \
                                          lookup/claim|        \ submit on miss
                                                      v         v
                                      Shared state (Redis)   Gateway (queue, pacer)
                                      cache + in-flight           |
                                                                  v
                                                    Simulated tool backend
```

Per search: normalize query to a key, check cache, check in-flight (wait if another worker is fetching), otherwise claim a lease and submit. The gateway rejects if the queue is full or the deadline cannot be met, re-checks the deadline before dispatch, paces calls, then writes the cache and wakes all waiters.

## 4. Problems we address (and how)
| Issue | Solution | Measured by |
|---|---|---|
| Retry storms | Retry budget, backoff with jitter, circuit breaker, merge retries of in-flight calls | Upstream calls per completed brief |
| Hotspots | Merging and caching absorb hot keys; skewed (Zipf) workloads | Throughput vs skew, queue depth |
| Stale reads | Per-tool TTL, ground-truth check in simulator | Stale-answer rate vs calls saved |
| Latent edge cases | In-flight lease so waiters take over if leader dies; one expiry does not cancel a shared call; explicit timeouts | Targeted tests, hung-request count |
| Hard-to-reproduce failures, debugging | Seeded replay, fault injection, trace ID across hops | Identical results across seeds |
| Clock skew | Deadlines travel as remaining time; only the gateway clock paces | Simulator spacing/overlap checks |

Optional (failover experiment only): split-brain (leader lease with fencing token), event ordering (idempotent result resolution), cache failure shifting load to the backend.

Out of scope, stated as limitations: consensus (Paxos/Raft), config-change blast radius, data residency, security hardening.

## 5. Experiments
Each setting is repeated 3 times; report median and range. Main metric: correct briefs completed before deadline per minute.

1. **Scaling ceiling.** No reuse; 1, 2, 4 workers; rising arrival rates. Find where throughput stops rising and the queue grows.
2. **Reuse.** No reuse vs cache vs cache + merge. Mostly-unique and highly-repeated workloads; fan-out k in {1, 3, 5, 10}; cold-cache burst; retry-storm run; TTL sweep.
3. **Humans vs agents (stretch).** Fixed human load plus growing agent fleet. Compare FIFO, human priority, reserved share. Measure human on-time rate, p95, agent throughput, fairness.
4. **Failover (optional).** Crash or pause the leader; measure recovery time, missed deadlines, pacing/concurrency violations.

Other metrics: upstream calls per completed brief (cost proxy), p95 latency, queue depth, rejected/expired/failed counts, stale-answer rate, wasted calls (calls spent on tasks that ultimately failed).

Workload extremes (for the proposal): base case is mostly unique searches at moderate rate; pathological case is a retry storm against a slow backend with a cold cache burst.

## 6. Roles
| Person | Owns |
|---|---|
| Sruthilaya | Agent scripts, brief assembly, query key, cache, in-flight merge and lease, stale check. Leads Experiment 2, verifies correctness. |
| Satyaa | Simulator (limits, fault injection, violation checks), gateway (bounded queue, deadline checks, pacer, retry budget, priority). Leads Experiments 3 and 4. |
| Muskan | Workflow API, worker deployment, replay harness, trace IDs and metrics, skewed workload generator, demo UI. Leads Experiment 1. |

## 7. Timeline
| Dates | Milestone |
|---|---|
| By 11/22 | Team fills charter facts; draft reviewed by all |
| 11/23 9am | Project Proposal and Team Charter PDF submitted |
| 11/24 - 11/27 (Thanksgiving week, lighter) | Contracts doc and shared types; synthetic corpus; simulator skeleton |
| 11/28 - 12/1 | One question end to end, no reuse (worker, gateway, simulator) |
| 12/2 - 12/7 | Cache, merge, lease; run Experiments 1 and 2; code freeze about 12/7 |
| 12/8 - 12/12 | Stretch experiments if stable; experiments PDF (max 5 pages); reflections |
| 12/13 | Buffer, repo cleanup, README |
| 12/14 9am | Final deliverables due |

## 8. AWS deployment (Learner Lab, 25 credits)
Local Docker Compose is the main dev loop, so no credits are spent while building. AWS is used for the final multi-host runs of Experiments 1 and 2 (and 3/4 if time allows).

| Component | AWS resource |
|---|---|
| Workers 1..N | One small EC2 instance each (t3.small/t3.medium) |
| Gateway + Redis | One EC2 instance, Redis as a container |
| Simulated backend | Its own EC2 instance, so gateway-to-backend is a real network hop |
| Replay harness + metrics | One EC2 instance (or laptop); results to files or S3 |

Rules:
- EC2 and S3 only. No NAT gateway, load balancer, ElastiCache or RDS (hourly cost, restricted roles).
- Use private IPs or an Elastic IP and keep addresses in one config file; IPs can change after a restart.
- Stop instances after every session; release unattached Elastic IPs and delete stray volumes.
- Check the credit balance before and after each experiment session and log it in `docs/project-management/LOG.md`.
- Sessions are time-limited and credentials rotate: runs must fit in a session or be restartable.
- Provide a script that brings the full stack up in minutes (owner: Muskan, milestone around 12/2).
- Record region, instance types and run durations for the experiments PDF.

Rough budget (estimates, verify in console): 6 small instances at about $0.12 to $0.25 per hour, so 20 hours of experiments is about $3 to $5 of 25 credits. Each teammate has a separate account and budget; decide whether one person hosts the stack or each runs a copy.

## 9. Risks
- Real-time pacing makes runs slow: add a configurable simulator time scale.
- Scope creep: Experiments 3 and 4 are stretch and can be dropped without hurting the core story.
- Integration risk: agree on `docs/contracts.md` and shared types first.
- Evidence for the problem is mostly practitioner posts: cite as stated problem, and state the simulated backend as a limitation.

## 10. Open decisions
- Who hosts the AWS stack (one account, or each teammate runs a copy); region.
- Confirm AI framing: scripted agents in tests, real LLM agents as future work.
- Confirm Redis as shared state.
- Confirm Experiment 3 as stretch and the support-style flow as headline scenario.
- Team facts for the charter: weekly hours, chat platform, response time, meeting schedule.
- Whether to build a quick prototype for preliminary results before 11/23.
