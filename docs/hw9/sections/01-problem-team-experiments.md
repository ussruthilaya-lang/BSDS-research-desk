# 1. Problem, Team, and Overview of Experiments

**1a. Problem and team.** Many users share a small search budget, and deep-research jobs use it up. A deep-research job answers one question with many agents. A lead agent splits the question into sub-questions. It starts several subagents in parallel, and each subagent runs several searches. Anthropic reports that its research system starts 3 to 5 subagents in parallel (Anthropic, 2025; see Section 4).

Every search from every subagent goes to a few providers that limit the request rate. For example, arXiv asks users of its legacy APIs for no more than one request every three seconds, with one connection at a time. The limit applies to all machines of one caller together (arXiv API terms of use; see Section 4).

One shared limit causes four problems. The budget runs out, because one wide job can need more calls than its deadline allows. Subagents repeat searches: Anthropic's early subagents "performed the exact same searches as other agents". A crashed or slow subagent holds up the whole job. Calls spent on an answer that arrives late are lost.

**Research Desk is the execution backend for deep-research jobs.** It schedules subagent tasks across workers. It shares search results in a cache and merges identical in-flight searches into one provider call. Every provider call goes through one paced gateway that rejects work that cannot finish. The backend gathers results by the deadline, and it restarts a crashed subagent from its last saved step. The goal is more correct briefs, finished on time, from a fixed provider budget.

The budget arithmetic shows why this matters. One call every three seconds gives at most 20 calls a minute. A job has N subagents, and each runs k searches. Without reuse, the job needs N times k calls. A fraction h of the searches comes from the cache or from merging. The system then finishes at most 20 / (N × k × (1 − h)) jobs a minute, for all users together.

| Job shape | Reuse | Most jobs a minute |
|---|---|---|
| N = 3, k = 5 | none (h = 0) | 20 / 15 = 1.33 |
| N = 3, k = 5 | half of searches (h = 0.5) | 20 / 7.5 = 2.67 |
| N = 10, k = 5 | none | one job needs 50 calls, which is 150 s at 3 s each, longer than a 120 s deadline |

Operators of deep-research products get more finished jobs from the same budget. Their users get answers on time and a fair share. Providers such as arXiv get no rule violations, fewer duplicate calls and no retry storms.

The project is a distributed system. Workers on separate machines run subagent tasks in parallel. Shared state in Redis (a fast in-memory database) holds the cache, the table of in-flight searches and the task leases. One gateway is the only caller of the provider. Any machine can crash while the system stays correct.

| Member | Role in the project | Background |
|---|---|---|
| Sruthilaya Umasankari Soma Shanmuga Sundaram | Job model, subagent runner, cache and merge, gather policy; leads experiments E2 and E3. Built the simulation prototype (event loop, workload generator, paced gateway, workers and the Experiment 1 runner, with tests) | MS Data Science student at Northeastern. Insights Analyst, then Senior CS Analyst, at Sentisum (Apr 2023 to Aug 2025): built and evaluated 15+ classification and sentiment models for 10+ enterprise clients, and designed an OpenAI-based QA scoring framework that reached about 80% agreement with human reviewers in a paid pilot. Personal projects include a medical claim-denial prediction pipeline (MLflow, FastAPI, Docker Compose, CI) and Rubrix, a RAG rubric auditor |
| Satyaa Sudarshan Guruswamy Sethuraman | Provider simulator, gateway, admission control, task leases and crash recovery, the public MCP service and its demo; leads experiment E4 | MS Computer Science student at Northeastern (expected December 2027). Machine Learning Engineer Intern at Ysquare Technology (Feb to Aug 2025): built a Python data pipeline for 200+ venues and designed a multi-agent architecture. Built LeaseBoston, an MCP server tested with real Claude sessions over stdio and HTTP and in Claude Desktop (github.com/1AlgoRythm/LeaseBoston). Coursework includes Distributed Systems and MLOps |
| Muskan Jain | Job API, workers, Docker Compose, replay harness, observability and the live control room, AWS deployment; leads experiment E1 and the simulator-versus-deployed check | MS Computer Science student at Northeastern (expected May 2027). Built an AI Grading Agent (RAG over ChromaDB, a ReAct grader-critic loop, hardened against prompt injection), deployed on Railway with Docker and a 271-test pytest suite run in CI on every push. Built AccessMapPlus, a Flask and MySQL platform with 40+ routes and a 10-table schema. Coursework includes Algorithms, DBMS and MLOps |

**1b. Overview of experiments, role of AI, and observability.** The experiments measure five results:

- **Throughput:** correct, complete briefs finished on time per minute.
- **Cost:** provider calls per brief, and wasted calls spent on jobs that did not finish correctly and on time.
- **Latency:** the 95th-percentile job latency.
- **Reuse:** cache and merge hit rates, and answers from an outdated corpus.
- **Resilience:** recovery time and duplicate calls after a worker crash.

One alarm covers all five. The provider simulator counts overlap and pacing violations. The count must be zero in every run. A non-zero count is a bug, not a result. Section 5 gives the sweeps and tradeoffs.

| Experiment | Question | Where it runs |
|---|---|---|
| E1 | Where does throughput stop rising, and does admission control stop the collapse past that point? | simulator, Docker Compose, a few AWS points |
| E2 | How much do the cache and merging save, and when? | simulator, Docker Compose, a few AWS points |
| E3 | Is a partial answer on time better than a complete answer late? | simulator only |
| E4 | Does a crashed worker cost the job? | Docker Compose, a few AWS points |

Two more experiments are future work and are not promised here: fairness between wide and narrow jobs, and failover of the gateway.

*Role of AI.* The lead agent and the subagents of a deep-research product are language-model agents. Research Desk treats them as a workload. All measured experiments replay scripted agents, so every run repeats exactly. Real Claude agents will appear only in the demonstration, through the Model Context Protocol (MCP, the standard way for an AI app to call outside tools). These runs will never count in a result. Section 2 gives the costs and benefits of building with Claude Code.

*Observability.* Every state change in every service will be one structured event with a trace identifier, a run identifier, the client and the user. The trace identifier rebuilds the timeline of one job. Prometheus counters will feed a Grafana dashboard. A live control room page will show the same events as they arrive. Section 5 describes the design.
