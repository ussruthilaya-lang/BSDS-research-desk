# 2. Project Plan and Recent Progress

**2a. Recent progress and timeline.** Since the first repository commit on 11/19 we have built the base that every experiment will run on, and we have agreed the shared interfaces between the three lanes, so the services can now be built in parallel.

- **Toy simulation (Sruthilaya, two merged pull requests).** A simulated clock, so a minute of traffic runs in milliseconds; a deterministic 200-paper corpus; a provider simulator that allows one call at a time with call starts at least 3 s apart and counts every violation of either rule; a seeded workload generator (Poisson arrivals, Zipf-skewed query popularity, k searches per job, a deadline per job); a FIFO gateway with a bounded queue, a pacer and a deadline check before every dispatch; worker slots; a metrics summary; and the Experiment 1 runner.
- **Shared contract (Satyaa).** Every endpoint, Redis key, event, metric and setting is named once, in `docs/contracts.md` and `src/researchdesk/contracts.py`, with tests that fail if the document and the code drift apart. Satyaa also froze the first Experiment 1 results as a baseline guarded by a test, and wrote one handoff file per person that lists tasks, dependencies and a checkable "done when" line.
- **Repository hygiene (Muskan).** The development extra and a continuous-integration workflow that runs the tests on every pull request (task M1) are ready for review.
- **First measured result.** Experiment 1 without reuse already shows a congestion collapse past the provider ceiling (Section 6). More than 110 automated tests pass on the main branch.

The work is split along three lanes, with task identifiers that match the handoff files:

| Person | Lane and tasks | Experiment led |
|---|---|---|
| Sruthilaya | Job model with N parallel subagents, fan-out and gather in the simulator, cache and in-flight merge (S2 to S4); the subagent runner and the lead in the service (S7, S8) | E2 (reuse), E3 (partial answer or late answer, simulator only) |
| Satyaa | Provider simulator service, gateway with admission control and retry budget, task leases and crash recovery, the MCP server and the live demo (T1 to T13) | E4 (worker crash) |
| Muskan | Job API, workers, Docker Compose and AWS scripts, replay harness, logs, metrics and dashboards, live control room (M1 to M12) | E1 (scaling ceiling and admission control) |

The timeline below uses targets, not gates. Only the proposal and the final deliverables have fixed due dates.

| Date (EST) | Milestone |
|---|---|
| Mon 11/23 | This proposal due (12:00 pm) |
| Tue 11/24 | Contract reviewed and approved by all three owners |
| Sun 11/29 | Simulation updated for deep-research jobs; E2 and E3 results on the simulator; services start in Compose |
| Sat 12/5 | Cache, merge, leases and admission control running in the services; E1 and E2 on Compose; AWS script works |
| Sun 12/6 | Build finished and every experiment run (simulator, Compose, and a few AWS points) |
| Fri 12/11 | Every deliverable ready to submit |
| Mon 12/14 | Final deliverables due (12:00 pm) and presentations (4 to 6 pm) |

**2b. AI in the project plan.** AI appears in two places and the costs and benefits differ. In the product, the lead agent and the subagents are LLM agents, and the backend treats them as a workload; the experiments replay scripted agents so that results repeat exactly, and real Claude agents appear only in the live demo. In development, the team uses a coding assistant (Claude Code) to scaffold code, draft tests and read documentation.

- **Benefits we expect and have seen.** Fast scaffolding: the whole toy simulation, with its tests, was committed over two days (11/20 and 11/21). Cheap exploration: when the first Experiment 1 run showed throughput collapsing, adding the wasted-call and backlog metrics to test the explanation took a few minutes.
- **Costs we expect.** Review time, because every change must be read by a person; plausible-looking code that is wrong; and subscription or token spending, which we have not yet measured and will log in the project-management log.
- **A cost we have already paid.** The assistant's first repository scaffold wrote its files with a hidden byte-order mark. That made `pyproject.toml` unreadable to the tools and quietly broke the first line of `.gitignore`. The first test run exposed it, and it was fixed in its own commit.
- **Mitigations.** Tests are written first and must stay green; every pull request is reviewed by a teammate before merging; the provider simulator's violation counters catch pacing bugs mechanically (they must read zero in every run); and a result is only reported after the metric that would disprove it has been measured.
