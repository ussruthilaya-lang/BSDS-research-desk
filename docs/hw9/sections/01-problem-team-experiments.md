# 1. Problem, Team, and Overview of Experiments

**1a. Problem and team.** Deep-research assistants answer one question with many agents. A lead agent splits the question into sub-questions and starts several subagents in parallel, and each subagent runs several searches. Anthropic reports that its research system has the lead agent spin up 3-5 subagents in parallel rather than serially (Anthropic, 2025; see Section 4). When many users run deep research at once, every search from every subagent lands on a few rate-limited providers. arXiv, for example, asks users of its legacy APIs for no more than one request every three seconds and one connection at a time, and applies the limit to all of a caller's machines as a whole (arXiv API terms of use; see Section 4).

Four problems follow from one shared limit. The budget runs out, because one wide job can need more calls than its deadline allows. Subagents repeat each other's searches (Anthropic's early subagents "performed the exact same searches as other agents"). A crashed or slow subagent stalls the whole answer. Calls spent on answers that arrive late are lost.

**Research Desk is the execution backend for deep-research jobs.** It schedules subagent tasks across workers, shares search results across subagents and users through a cache, merges identical in-flight searches into one provider call, sends every provider call through one paced gateway that rejects work that cannot finish, gathers results by the deadline, and restarts a crashed subagent from its last saved step. The goal is that more correct research briefs finish on time under a fixed provider budget.

The budget arithmetic shows why this matters. At one call every three seconds the system can start at most 20 calls a minute. A job with N subagents that each run k searches needs N times k calls if nothing is reused. If a fraction h of searches is answered by the cache or by merging, the system finishes at most 20 divided by (N times k times (1 minus h)) jobs a minute, for all users together.

| Job shape | Reuse | Most jobs a minute |
|---|---|---|
| N = 3, k = 5 | none (h = 0) | 20 / 15 = 1.33 |
| N = 3, k = 5 | half of searches (h = 0.5) | 20 / 7.5 = 2.67 |
| N = 10, k = 5 | none | one job needs 50 calls, which is 150 s at 3 s each, longer than a 120 s deadline |

The stakeholders are the operators of deep-research products (more finished jobs from the same budget and a predictable cost), their users (answers on time and a fair share when others run very wide jobs), and providers such as arXiv (no rule violations, fewer duplicate calls, no retry storms). The project is a distributed system because workers on separate machines run subagent tasks in parallel, shared state in Redis holds the cache, the in-flight table and the task leases, one gateway is the only caller of the provider, and every machine can crash while the system stays correct.

| Member | Role in the project | Background |
|---|---|---|
| Sruthilaya Umasankari Soma Shanmuga Sundaram | Job model, subagent runner, cache and merge, gather policy; leads experiments E2 and E3. Built the simulation prototype (event loop, workload generator, paced gateway, workers and the Experiment 1 runner, with tests) | TODO(Sruthilaya: two lines about your background) |
| Satyaa Sudarshan Guruswamy Sethuraman | Provider simulator, gateway, admission control, task leases and crash recovery, the public MCP service and its demo; leads experiment E4 | MS Computer Science student at Northeastern (expected May 2027). Machine Learning Engineer Intern at Ysquare Technology (Feb to Aug 2025): built a Python data pipeline for 200+ venues and designed a multi-agent architecture. Built LeaseBoston, an MCP server tested with real Claude sessions over stdio and HTTP and in Claude Desktop (github.com/1AlgoRythm/LeaseBoston). Coursework includes Distributed Systems and MLOps |
| Muskan Jain | Job API, workers, Docker Compose, replay harness, observability and the live control room, AWS deployment; leads experiment E1 and the simulator-versus-deployed check | MS Computer Science student at Northeastern (expected May 2027). Built an AI Grading Agent (RAG over ChromaDB, a ReAct grader-critic loop, hardened against prompt injection), deployed on Railway with Docker and a 271-test pytest suite run in CI on every push. Built AccessMapPlus, a Flask and MySQL platform with 40+ routes and a 10-table schema. Coursework includes Algorithms, DBMS and MLOps |

**1b. Overview of experiments, role of AI, and observability.** The experiments evaluate five kinds of result: throughput (correct, complete briefs finished on time per minute), cost (provider calls per brief, and wasted calls spent on jobs that did not finish correctly and on time), latency (95th-percentile job latency), reuse (cache and merge hit rates, and answers served from an outdated corpus), and resilience (recovery time and duplicate calls after a worker crash). A correctness alarm runs through all of them: the provider simulator counts overlap and pacing violations, and the count must be zero in every run, so a non-zero count is a bug and not a result. Section 5 gives the sweeps and tradeoffs.

| Experiment | Question | Where it runs |
|---|---|---|
| E1 | Where does throughput stop rising, and does admission control stop the collapse past that point? | simulator, Docker Compose, a few AWS points |
| E2 | How much do the cache and merging save, and when? | simulator, Docker Compose, a few AWS points |
| E3 | Is a partial answer on time better than a complete answer late? | simulator only |
| E4 | Does a crashed worker cost the job? | Docker Compose, a few AWS points |

Two further experiments, fairness between wide and narrow jobs and failover of the gateway, are future work and are not promised here.

*Role of AI.* The lead agent and the subagents of a deep-research product are language-model agents. Research Desk treats them as a workload and does no model reasoning itself. All measured experiments replay scripted agents, so every run can be repeated exactly. Real Claude agents appear only in the demonstration: the backend runs as a live service that a Claude Desktop or Claude Code user connects to through the Model Context Protocol, and those runs are never counted in a result. The team also builds with Claude Code; its costs and benefits are in Section 2.

*Observability.* Every state change in every service is recorded as one structured event that carries a trace identifier, a run identifier, the client and the user, so one job's whole timeline can be rebuilt from its trace identifier. Prometheus counters feed a Grafana dashboard for numbers over time, and a live control room page shows the same events as they arrive: violations, queue depth, calls a minute against the limit, cache hit rate, a progress bar for every subagent, and worker leases. Section 5 describes the design.
