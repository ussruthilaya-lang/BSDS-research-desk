# 6. Preliminary Results

**6a. Preliminary results and what remains.** We have measured part of Experiment 1 and a first, reduced version of Experiment 2, both with one subagent per job. Experiment 1 comes first. It runs on the toy simulation with a simulated clock (`python prototype/exp1.py`, frozen as `results/prototype/exp1_baseline_2026-11-22.csv`). Each job runs 5 searches in order, with an 8 s pause between searches (an agent reading results and refining its query) and a 120 s deadline. The provider allows one call at a time with starts at least 3 s apart, so at most 20 calls a minute. Each setting simulates 30 minutes and is repeated with 3 seeds. The provider simulator counted zero pacing or overlap violations in all 24 settings.

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

**Experiment 2, first comparison.** `python prototype/exp2.py` (frozen as `results/prototype/exp2_prelim_2026-11-22.csv`) compares no reuse, a cache with a 10-minute lifetime, and the cache plus merging of identical searches that are in flight at the same time. Jobs and assumptions are the same as in Experiment 1 (5 searches, 8 s pause, 120 s deadline, 1 s provider latency), 3 seeds per setting, medians with the best and worst seed in brackets. Three workloads:

- **Mostly unique:** 4 workers, 6 arrivals a minute for 30 simulated minutes, a pool of 5000 queries.
- **Highly repeated:** the same load with a pool of only 30 queries and Zipf skew 1.2.
- **Cold burst:** 12 workers and 24 jobs arriving within about 12 s on an empty cache, over a 10-minute window (briefs per minute there is the count divided by 10).

6 arrivals a minute is above the no-reuse ceiling of 4 briefs a minute, so these runs show whether reuse lifts the ceiling.

| Workload | Reuse | Briefs per min | Briefs on time | Provider calls | Calls per brief | Cache hits | Merged searches | Expired jobs |
|---|---|---|---|---|---|---|---|---|
| Mostly unique | none | 1.67 (1.00 to 1.80) | 50 | 591 | 11.92 | 0 | 0 | 106 |
| Mostly unique | cache | 1.80 (1.20 to 1.90) | 54 | 589 | 11.02 | 25 | 0 | 96 |
| Mostly unique | cache and merge | 1.80 (1.20 to 1.90) | 54 | 589 | 11.02 | 25 | 0 | 96 |
| Highly repeated | none | 1.67 (1.00 to 1.80) | 50 | 591 | 11.92 | 0 | 0 | 106 |
| Highly repeated | cache | 4.37 (4.20 to 5.23) | 131 | 82 | 0.63 | 758 | 0 | 5 |
| Highly repeated | cache and merge | 4.43 (4.20 to 5.23) | 133 | 81 | 0.61 | 758 | 1 | 5 |
| Cold burst | none | 0.00 (0.00 to 0.00) | 0 | 44 | no brief finished | 0 | 0 | 24 |
| Cold burst | cache | 2.10 (1.30 to 2.20) | 21 | 36 | 1.71 | 84 | 0 | 0 |
| Cold burst | cache and merge | 2.40 (2.40 to 2.40) | 24 | 25 | 1.04 | 84 | 11 | 0 |

What the comparison shows:

- **Reuse only pays when searches repeat.** With mostly unique searches, 25 of the 614 searches that reached the cache or the provider were cache hits (about 4%), and throughput moved from 1.67 to 1.80, inside the seed range. With no reuse the repetition of searches makes no difference, which is why both "none" rows are identical.
- **When searches repeat, the cache lifts the ceiling.** Throughput rose from 1.67 to 4.37 briefs a minute, above the 4 a minute no-reuse ceiling, because provider calls fell from 591 to 82 (a hit fraction of about 0.9). Calls per brief fell from 11.92, when most calls went to jobs that expired, to 0.63.
- **Merging adds nothing measurable in steady state.** 4.43 against 4.37 briefs a minute is inside the seed range, and only one search was merged: once the cache is warm it already holds the answer.
- **Merging matters on a cold burst.** The 24 jobs need 120 searches, which take 360 s at 3 s apart against a 120 s deadline, so with no reuse none finishes in time and all 44 calls made are wasted. The cache alone finishes 21 jobs with 36 calls. The cache plus merging finishes all 24 with 25 calls, and 11 searches were merged. The seed ranges do not overlap (2.40 against 1.30 to 2.20).
- **Correctness and limits held.** No wrong brief was returned and the provider simulator counted zero violations in all 9 settings.

Limitations: jobs have one subagent, so fan-out is not tested; the corpus never changes, so every cached answer is fresh by construction and the staleness cost of a long cache lifetime is not measured; the 10-minute lifetime is a proposed default; the burst has only 24 jobs and 3 seeds; and the simulation is not the deployed system.

**What we have not collected yet.** No results exist yet for Experiments 3 or 4. Experiment 1 has not yet been run with admission control or with fan-out, and Experiment 2 has not yet been run with fan-out, with corpus versions (so staleness is unmeasured), or on the deployed system. For fan-out we can state what the arithmetic allows. If each job has N subagents of 3 searches and a fraction h of searches is served by the cache or by merging, the jobs per minute the provider can finish are at most 20 / (N × 3 × (1 − h)). These are upper bounds from arithmetic, not measurements:

| Subagents per job (N) | h = 0 (no reuse) | h = 0.5 |
|---|---|---|
| 1 | 6.67 | 13.33 |
| 3 | 2.22 | 4.44 |
| 5 | 1.33 | 2.67 |
| 10 | 0.67 | 1.33 |

The first comparison above is the one-subagent case. The full Experiment 2 will show how close the cache and merging get to these bounds with fan-out, and when staleness or waiting for a merged call costs more than it saves. Remaining work, by owner and target date:

| Experiment | Remaining work | Owner | Target |
|---|---|---|---|
| E1 | Add fan-out and admission control (off and on); full sweep on the simulator; 3 points on Compose and AWS | Muskan | Sun 12/6 |
| E2 | Fan-out (N subagents per job), corpus versions for staleness and a cache-lifetime sweep in the simulator; full sweep; a few points on Compose and AWS | Sruthilaya | Sun 11/29 (simulator), Sun 12/6 (deployed) |
| E3 | Partial answer against complete answer late, on the simulator only | Sruthilaya | Sun 11/29 |
| E4 | Kill a worker mid-subagent, with leases and checkpoints off and on, on Compose and AWS | Satyaa | Sun 12/6 |

**6b. Base-case and worst-case workloads.** The base case is a moderate arrival rate below the provider ceiling, jobs of N = 3 subagents with k = 3 searches each, mostly unique topics, a warm cache and normal provider latency. We choose it because the system should do well there: nearly every job should finish complete and on time, so it is the reference point for every comparison, and it is the workload on which we will check that the simulator and the deployed system agree. The measured baseline already supports this choice, since below the ceiling the measured runs lose almost no calls (3 wasted calls at 3 arrivals a minute with 4 workers).

The pathological worst case is a burst of wide jobs (N = 10 subagents, k = 5 searches) arriving on a cold cache while the provider is slow and clients retry. We choose it because the demand is far beyond the budget, and each mechanism has to prove itself against it:

- One wide job needs 50 calls, which take at least 150 s at 3 s apart. That is longer than a 120 s deadline even with no other traffic, so without reuse or a partial answer it cannot finish.
- If the provider's latency grows from the simulator's 1 s to 5 s, the one-call-at-a-time rule becomes the limit, and the budget drops from 20 to 12 calls a minute.
- A cold cache means merging is the only reuse available at the start of the burst.
- Retries add load exactly when the provider is struggling.

Without admission control the baseline above already wastes about nine calls in ten under overload. This workload is where admission control, merging and the partial-answer gather each prove their worth, or fail to.
