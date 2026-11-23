# 2. Project Plan and Recent Progress

**2a. Recent progress and timeline.** The first repository commit was on 11/19. Since then we have built the base that every experiment will run on. We have also agreed the shared interfaces between the three lanes. The services can now be built in parallel.

- **Toy simulation (Sruthilaya, two merged pull requests).** A simulated clock, so a minute of traffic runs in milliseconds. A deterministic 200-paper corpus. A provider simulator that allows one call at a time, with starts at least 3 s apart, and counts every violation. A seeded workload generator (Poisson arrivals, Zipf-skewed query popularity, k searches per job, a deadline per job).

  The simulation also has a FIFO gateway with a bounded queue, a pacer and a deadline check before every dispatch. It has worker slots, a metrics summary and the Experiment 1 runner. A cache and in-flight merge layer has a first Experiment 2 runner.
- **Shared contract (Satyaa).** Every endpoint, Redis key, event, metric and setting is named once, in `docs/contracts.md` and `src/researchdesk/contracts.py`. Tests fail if the document and the code drift apart. Satyaa also froze the first Experiment 1 results as a baseline, guarded by a test. Satyaa wrote one handoff file per person. It lists tasks, dependencies and a checkable "done when" line.
- **Repository hygiene (Muskan).** The development extra and a continuous-integration workflow are ready for review (task M1). The workflow runs the tests on every pull request.
- **First measured results.** Experiment 1 without reuse shows a congestion collapse past the provider ceiling. A first Experiment 2 comparison shows two effects. The cache lifts the ceiling when searches repeat. Merging finishes a cold burst that the cache alone cannot (Section 6). More than 110 automated tests pass on the main branch.

The work is split along three lanes. Section 10 lists them, and the handoff files in the repository give every task identifier.

The timeline uses targets, not gates. Only the proposal and the final deliverables have fixed due dates.

| Date (EST) | Milestone |
|---|---|
| Mon 11/23 | This proposal due (12:00 pm) |
| Tue 11/24 | Contract reviewed and approved by all three owners |
| Sun 11/29 | Simulation updated for deep-research jobs; E2 and E3 results on the simulator; services start in Compose |
| Sat 12/5 | Cache, merge, leases and admission control running in the services; E1 and E2 on Compose; AWS script works |
| Sun 12/6 | Build finished and every experiment run (simulator, Compose, and a few AWS points) |
| Fri 12/11 | Every deliverable ready to submit |
| Mon 12/14 | Final deliverables due (12:00 pm) and presentations (4 to 6 pm) |

**2b. AI in the project plan.** AI appears in two places. In the product, the lead agent and the subagents are LLM agents, and the backend treats them as a workload. The experiments replay scripted agents, so results repeat exactly. Real Claude agents appear only in the live demo. In development, the team uses a coding assistant (Claude Code) to scaffold code, draft tests and read documentation.

- **Benefits we have seen.** Fast scaffolding: the whole toy simulation, with its tests, was committed over two days (11/20 and 11/21). Cheap exploration: when the first Experiment 1 run showed throughput collapsing, adding the wasted-call and backlog metrics took a few minutes.
- **Costs we expect.** Review time, because a person must read every change. Wrong code that looks right. Subscription or token spending, which we have not measured yet and will log in the project-management log.
- **A cost already paid.** The assistant's first repository scaffold wrote its files with a hidden byte-order mark. It made `pyproject.toml` unreadable to the tools and quietly broke the first line of `.gitignore`. The first test run exposed it, and it was fixed in its own commit.
- **Mitigations.** Tests are written first and must stay green. A teammate reviews every pull request. The provider simulator's violation counters catch pacing bugs mechanically, and they must read zero in every run. A result is reported only after the metric that would disprove it has been measured.
