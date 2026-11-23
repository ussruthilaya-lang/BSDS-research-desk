# Handoff: who builds what

Written 2026-11-22. One file per person. Each file says what you build, what you hand to the others,
what you need from them, and the order to work in.

| Person | File | Lane | Leads |
|---|---|---|---|
| Sruthilaya | [sruthilaya.md](sruthilaya.md) | job model, subagent runner, cache and merge, gather | E2, E3 (simulator) |
| Satyaa | [satyaa.md](satyaa.md) | provider simulator, gateway, admission, leases, MCP server, demo | E4 |
| Muskan | [muskan.md](muskan.md) | Job API, workers, Compose, harness, observability, live control room, AWS | E1, simulator-vs-real check |

## How to use this with Claude Code

1. Open a terminal at the repo root and start `claude`. The root `CLAUDE.md` loads by itself; it
   holds the shared rules.
2. First message: `Read docs/handoff/<your name>.md and docs/contracts.md, then start the first task
   that is not done. Write the tests first.`
3. Track status in GitHub issues (one per task ID), not by editing someone else's handoff file.

## Experiments (this numbering replaces README.md and docs/PLAN.md)

| # | Question | Where it runs | Lead |
|---|---|---|---|
| E1 | Where does throughput stop rising, and does admission control stop the collapse after it? | simulator, Compose, a few AWS points | Muskan |
| E2 | How much do the cache and merging save, and when? | simulator, Compose, a few AWS points | Sruthilaya |
| E3 | Is a partial answer on time better than a complete answer late? | **simulator only** | Sruthilaya |
| E4 | Does a crashed worker cost the job? Leases off vs on, three lease lengths | Compose, a few AWS points | Satyaa |
| E5, E6 | Fairness; gateway failover | **future work, not promised** | — |

Every setting runs with seeds 0, 1 and 2; report the median and the range.

**Workloads (HW9 item 6b):**
- **Base case:** a moderate arrival rate below the ceiling, N = 3 subagents, k = 3 searches each,
  mostly unique topics, warm cache, `slowdown` 1.0. Most jobs should finish complete and on time.
- **Worst case:** a burst of wide jobs (N = 10, k = 5), cold cache, `slowdown` 5.0, retries on.
  Calls needed far exceed 20 a minute; the queue fills; calls go to jobs that will fail anyway.

**Simulator vs deployed:** a deployed result agrees when its median `briefs_per_min` is within 15%
of the simulator's on the same workload file (proposed; confirm as a team).

**Experiment 1 baseline:** `results/prototype/exp1_baseline_2026-11-22.csv`, guarded by
`tests/test_prototype_baseline.py`. Never edit it; add a new dated file if E1 is meant to change.

## The order things fit together

1. **Contract** (`docs/contracts.md`): drafted. Each owner reviews their sections and approves the
   PR (S6, T3, M2).
2. **Simulator v2** in `prototype/`: job model (S2), fan-out and gather (S3), cache and merge (S4),
   versioned corpus and latency (T1), admission (T6). Fast, so E1 to E3 sweeps run here first.
3. **Services**, built in parallel against the contract, each with stubs for the others: provider
   (T4), gateway (T5), Job API (M3), runner (S7), worker (M4), leases (T7), Compose (M5).
4. **Joined up:** one job end to end on Compose, then cache, merge, leases and admission.
5. **Measured:** harness (M6), E1, E2 and E4 on Compose and a few AWS points (M9, S9, T8).
6. **Shown:** live control room (M12); the **public MCP service** anyone's Claude Desktop can add
   through the Cloudflare tunnel, with per-user quotas (T12, T6); optional progress card (T12b); the
   demo video with two users at once (T13). The service is live on demand, while a lab session runs.
7. **Written:** report, poster, blog post, slides (S10, T11, M11).

Nothing waits for a checkpoint: start your next task as soon as its inputs exist, using stubs
behind the contract until the real thing lands.

## Dates (EST)

| Date | What |
|---|---|
| Mon 11/23, 12:00 pm | HW9 due (one PDF, Satyaa submits; everyone joins the project group on Canvas People first) |
| Mon 11/30, 12:00 pm | Assignment 10 due (individual) |
| Sun 12/6 | Target: build finished, every experiment run |
| Week of 12/7 | Final Mastery (individual, 15%): keep it free of build work |
| Fri 12/11 | Target: every deliverable ready |
| Mon 12/14, 12:00 pm | Final deliverables due: poster, blog report or paper, code repository, presentation |
| Mon 12/14, 4–6 pm | Final presentations |
