# 6. Preliminary Results

**6a. Preliminary results and what remains.** We have measured one part of Experiment 1 so far: the no-reuse case with one subagent per job. It runs on the toy simulation with a simulated clock (`python prototype/exp1.py`, frozen as `results/prototype/exp1_baseline_2026-11-22.csv`). Each job runs 5 searches in order, with an 8 s pause between searches (an agent reading results and refining its query) and a 120 s deadline. The provider allows one call at a time with starts at least 3 s apart, so at most 20 calls a minute. Each setting simulates 30 minutes and is repeated with 3 seeds. The provider simulator counted zero pacing or overlap violations in all 24 settings.

![Briefs completed on time per minute against arrival rate for 1, 2 and 4 workers. Throughput rises with workers up to a peak of 3.27 briefs per minute for 4 workers at 4 arrivals per minute, just under the 4 per minute provider ceiling, then falls to 0.27 at 12 arrivals per minute.](../../results/prototype/exp1_briefs_per_min.png)

<p class="caption">Figure 1. Experiment 1 without reuse: median briefs completed on time per minute, with the best and worst of 3 seeds as a band.</p>

Median briefs completed on time per minute (the data behind Figure 1):

| Arrivals per min | 1 worker | 2 workers | 4 workers |
|---|---|---|---|
| 1 | 0.83 | 0.97 | 0.97 |
| 2 | 0.80 | 1.77 | 1.90 |
| 3 | 0.40 | 1.97 | 2.77 |
| 4 | 0.23 | 1.33 | 3.27 |
| 5 | 0.17 | 0.83 | 2.23 |
| 6 | 0.17 | 0.60 | 1.67 |
| 8 | 0.10 | 0.37 | 0.73 |
| 12 | 0.07 | 0.20 | 0.27 |

The same runs for 4 workers, showing where the calls go:

| Arrivals per min | Briefs per min, median (range) | Expired jobs | Wasted calls | Peak jobs waiting for a worker |
|---|---|---|---|---|
| 1 | 0.97 (0.70 to 1.20) | 0 | 1 | 1 |
| 2 | 1.90 (1.87 to 1.93) | 0 | 0 | 2 |
| 3 | 2.77 (2.63 to 2.87) | 0 | 3 | 5 |
| 4 | 3.27 (3.13 to 3.50) | 9 | 52 | 8 |
| 5 | 2.23 (2.00 to 2.47) | 61 | 243 | 12 |
| 6 | 1.67 (1.00 to 1.80) | 106 | 346 | 16 |
| 8 | 0.73 (0.47 to 0.87) | 179 | 484 | 22 |
| 12 | 0.27 (0.27 to 0.33) | 311 | 554 | 32 |

What the measurements show:

- **The provider ceiling holds.** With 5 calls per brief, 20 calls a minute allows at most 4 briefs a minute. No median exceeds it, and the best is 3.27 (4 workers at 4 arrivals a minute).
- **Workers help until the budget binds.** At 3 arrivals a minute, 1, 2 and 4 workers finish 0.40, 1.97 and 2.77 briefs a minute.
- **Past the ceiling, throughput collapses instead of flattening.** For 4 workers, going from 4 to 12 arrivals a minute drops output from 3.27 to 0.27 briefs a minute. Wasted calls, meaning calls that did not end up in a correct on-time brief, rise from 52 to 554 of the roughly 600 calls the provider could serve in 30 minutes. A plain FIFO queue lets jobs wait until most of their deadline is gone, start anyway, and expire part-way through their searches. We tested this explanation by adding the wasted-call and backlog measurements, and they match it. This is the failure that admission control in Experiment 1 must fix.
- **The queue forms in the wrong place for deep research.** The gateway queue peaked at 2 requests in the median run, and can never exceed the number of workers, because each worker runs one job's searches one at a time. The backlog built up in front of the workers instead, with a median peak of 32 waiting jobs at 4 workers and 12 arrivals a minute. With parallel subagents we expect the gateway's bounded queue and admission control to become the bottleneck. That is a prediction for Experiment 1 with fan-out, not a result.

Limitations of these numbers: the clock and the provider are simulated, the 8 s pause and the 120 s deadline are workload assumptions and not measurements, jobs have a single subagent, and the corpus is synthetic.

**What we have not collected yet.** No results exist yet for Experiments 2, 3 or 4, and Experiment 1 has not yet been run with admission control or with fan-out. For Experiment 2 we can state what the arithmetic allows. If each job has N subagents of 3 searches and a fraction h of searches is served by the cache or by merging, the jobs per minute the provider can finish are at most 20 / (N × 3 × (1 − h)). These are upper bounds from arithmetic, not measurements:

| Subagents per job (N) | h = 0 (no reuse) | h = 0.5 |
|---|---|---|
| 1 | 6.67 | 13.33 |
| 3 | 2.22 | 4.44 |
| 5 | 1.33 | 2.67 |
| 10 | 0.67 | 1.33 |

Experiment 2 will show how close the cache and merging get to these bounds, and when staleness or waiting for a merged call costs more than it saves. Remaining work, by owner and target date:

| Experiment | Remaining work | Owner | Target |
|---|---|---|---|
| E1 | Add fan-out and admission control (off and on); full sweep on the simulator; 3 points on Compose and AWS | Muskan | Sun 12/6 |
| E2 | Cache and merge in the simulator; full sweep on the simulator; a few points on Compose and AWS | Sruthilaya | Sun 11/29 (simulator), Sun 12/6 (deployed) |
| E3 | Partial answer against complete answer late, on the simulator only | Sruthilaya | Sun 11/29 |
| E4 | Kill a worker mid-subagent, with leases and checkpoints off and on, on Compose and AWS | Satyaa | Sun 12/6 |

**6b. Base-case and worst-case workloads.** The base case is a moderate arrival rate below the provider ceiling, jobs of N = 3 subagents with k = 3 searches each, mostly unique topics, a warm cache and normal provider latency. We choose it because the system should do well there: nearly every job should finish complete and on time, so it is the reference point for every comparison, and it is the workload on which we will check that the simulator and the deployed system agree. The measured baseline already supports this choice, since below the ceiling the measured runs lose almost no calls (3 wasted calls at 3 arrivals a minute with 4 workers).

The pathological worst case is a burst of wide jobs (N = 10 subagents, k = 5 searches) arriving on a cold cache while the provider is slow and clients retry. We choose it because the demand is far beyond the budget, and each mechanism has to prove itself against it:

- One wide job needs 50 calls, which take at least 150 s at 3 s apart. That is longer than a 120 s deadline even with no other traffic, so without reuse or a partial answer it cannot finish.
- If the provider's latency grows from the simulator's 1 s to 5 s, the one-call-at-a-time rule becomes the limit, and the budget drops from 20 to 12 calls a minute.
- A cold cache means merging is the only reuse available at the start of the burst.
- Retries add load exactly when the provider is struggling.

Without admission control the baseline above already wastes about nine calls in ten under overload. This workload is where admission control, merging and the partial-answer gather each prove their worth, or fail to.
