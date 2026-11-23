# 6. Preliminary Results

**6a. Preliminary results and what remains.** We have measured part of Experiment 1 and a first, reduced version of Experiment 2. Both use one subagent per job.

*Experiment 1 setup.* It runs on the toy simulation with a simulated clock (`python prototype/exp1.py`, frozen as `results/prototype/exp1_baseline_2026-11-22.csv`).

- Each job runs 5 searches in order. An 8 s pause between searches stands for an agent that reads results and refines its query. Each job has a 120 s deadline.
- The provider allows one call at a time, with starts at least 3 s apart. That is at most 20 calls a minute.
- Each setting simulates 30 minutes and is repeated with 3 seeds.
- The provider simulator counted zero pacing or overlap violations in all 24 settings.

![Briefs completed on time per minute against arrival rate for 1, 2 and 4 workers. Throughput rises with workers up to a peak of 3.27 briefs per minute for 4 workers at 4 arrivals per minute, just under the 4 per minute provider ceiling, then falls to 0.27 at 12 arrivals per minute.](../../results/prototype/exp1_briefs_per_min.png)

<p class="caption">Figure 1. Experiment 1 without reuse: median briefs completed on time per minute, with the best and worst of 3 seeds as a band.</p>

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

- **The provider ceiling holds.** With 5 calls per brief, 20 calls a minute allows at most 4 briefs a minute. No median is above it. The best is 3.27 (4 workers at 4 arrivals a minute).
- **Workers help until the budget binds.** At 3 arrivals a minute, 1, 2 and 4 workers finish 0.40, 1.97 and 2.77 briefs a minute.
- **Past the ceiling, throughput collapses.** For 4 workers, output drops from 3.27 to 0.27 briefs a minute as arrivals go from 4 to 12 a minute. Wasted calls (calls that did not end up in a correct on-time brief) rise from 52 to 554, out of about 600 that the provider can serve in 30 minutes.
- **The cause is the FIFO queue.** A first-in, first-out queue lets jobs wait until most of their deadline is gone. The jobs start anyway and expire part-way through their searches. The wasted-call and backlog numbers match this explanation. Admission control in Experiment 1 must fix it.
- **The queue forms in front of the workers, not at the gateway.** The gateway queue peaked at 2 requests. The median peak was 32 waiting jobs. With parallel subagents, we predict that the gateway queue becomes the bottleneck. This is a prediction, not a result.

Limitations: the clock and the provider are simulated, the 8 s pause and the 120 s deadline are assumptions, jobs have one subagent, and the corpus is synthetic.

*Experiment 2, first comparison.* `python prototype/exp2.py` (frozen as `results/prototype/exp2_prelim_2026-11-22.csv`) compares three set-ups: no reuse, a cache with a 10-minute lifetime, and the cache plus merging of identical searches that are in flight at the same time. The jobs and assumptions are the same as in Experiment 1 (5 searches, 8 s pause, 120 s deadline, 1 s provider latency). Each setting has 3 seeds. The table gives medians, with the best and worst seed in brackets. There are three workloads:

- **Mostly unique:** 4 workers, 6 arrivals a minute for 30 simulated minutes, and a pool of 5000 queries.
- **Highly repeated:** the same load, with a pool of only 30 queries and Zipf skew 1.2.
- **Cold burst:** 12 workers and 24 jobs that arrive within about 12 s on an empty cache, over a 10-minute window. Briefs per minute there is the count divided by 10.

6 arrivals a minute is above the no-reuse ceiling of 4 briefs a minute. These runs therefore show whether reuse lifts the ceiling.

| Workload | Reuse | Briefs/min | On time | Calls | Calls/brief | Hits | Merged | Expired |
|---|---|---|---|---|---|---|---|---|
| Unique | none | 1.67 (1.00 to 1.80) | 50 | 591 | 11.92 | 0 | 0 | 106 |
| Unique | cache | 1.80 (1.20 to 1.90) | 54 | 589 | 11.02 | 25 | 0 | 96 |
| Unique | both | 1.80 (1.20 to 1.90) | 54 | 589 | 11.02 | 25 | 0 | 96 |
| Repeated | none | 1.67 (1.00 to 1.80) | 50 | 591 | 11.92 | 0 | 0 | 106 |
| Repeated | cache | 4.37 (4.20 to 5.23) | 131 | 82 | 0.63 | 758 | 0 | 5 |
| Repeated | both | 4.43 (4.20 to 5.23) | 133 | 81 | 0.61 | 758 | 1 | 5 |
| Burst | none | 0.00 (0.00 to 0.00) | 0 | 44 | none | 0 | 0 | 24 |
| Burst | cache | 2.10 (1.30 to 2.20) | 21 | 36 | 1.71 | 84 | 0 | 0 |
| Burst | both | 2.40 (2.40 to 2.40) | 24 | 25 | 1.04 | 84 | 11 | 0 |

Columns: briefs a minute (median, with range), briefs on time, provider calls, calls per brief, cache hits, merged searches and expired jobs. The workloads are Unique (mostly unique), Repeated (highly repeated) and Burst (cold burst). "Both" means the cache plus merging.

What the comparison shows:

- **Reuse pays only when searches repeat.** With mostly unique searches, only 25 of 614 searches (about 4%) were cache hits. Throughput moved from 1.67 to 1.80, inside the seed range.
- **When searches repeat, the cache lifts the ceiling.** Throughput rose from 1.67 to 4.37 briefs a minute, above the no-reuse ceiling of 4. Provider calls fell from 591 to 82. Calls per brief fell from 11.92 to 0.63.
- **Merging adds nothing in steady state.** 4.43 against 4.37 is inside the seed range. Once the cache is warm, it already holds the answer.
- **Merging matters on a cold burst.** The 24 jobs need 120 searches, which take 360 s at 3 s apart, against a 120 s deadline. With no reuse, no job finishes, and all 44 calls are wasted. The cache alone finishes 21 jobs with 36 calls. The cache plus merging finishes all 24 with 25 calls. The seed ranges do not overlap (2.40 against 1.30 to 2.20).
- **Correctness held.** No wrong brief was returned. The provider simulator counted zero violations in all 9 settings.

Limitations: jobs have one subagent, the corpus never changes (so staleness is not measured), the 10-minute lifetime is a proposed default, the burst has only 24 jobs, and the simulation is not the deployed system.

*What we have not collected yet.* There are no results for Experiments 3 or 4. Experiment 1 has not run with admission control or fan-out. Experiment 2 has not run with fan-out, with corpus versions, or on the deployed system.

For fan-out, arithmetic gives an upper bound. Each job has N subagents of 3 searches. A fraction h of searches comes from the cache or from merging. The provider then finishes at most 20 / (N × 3 × (1 − h)) jobs a minute:

| Subagents per job (N) | h = 0 (no reuse) | h = 0.5 |
|---|---|---|
| 1 | 6.67 | 13.33 |
| 3 | 2.22 | 4.44 |
| 5 | 1.33 | 2.67 |
| 10 | 0.67 | 1.33 |

The full Experiment 2 will show how close the cache and merging get to these bounds with fan-out. The remaining work, by owner and target date:

| Experiment | Remaining work | Owner | Target |
|---|---|---|---|
| E1 | Add fan-out and admission control (off and on); full sweep on the simulator; 3 points on Compose and AWS | Muskan | Sun 12/6 |
| E2 | Fan-out (N subagents per job), corpus versions for staleness and a cache-lifetime sweep in the simulator; full sweep; a few points on Compose and AWS | Sruthilaya | Sun 11/29 (simulator), Sun 12/6 (deployed) |
| E3 | Partial answer against complete answer late, on the simulator only | Sruthilaya | Sun 11/29 |
| E4 | Kill a worker mid-subagent, with leases and checkpoints off and on, on Compose and AWS | Satyaa | Sun 12/6 |

**6b. Base-case and worst-case workloads.** The base case is a moderate arrival rate below the provider ceiling. Jobs have N = 3 subagents with k = 3 searches each. Topics are mostly unique, the cache is warm and provider latency is normal. We choose it because the system should do well there: nearly every job should finish complete and on time.

It is the reference point for every comparison, and the place where we check that the simulator and the deployed system agree. The measured baseline supports this choice: below the ceiling, the runs lose almost no calls (3 wasted calls at 3 arrivals a minute with 4 workers).

The worst case is a burst of wide jobs (N = 10, k = 5) on a cold cache, with a slow provider and clients that retry. We choose it because the demand is far beyond the budget:

- One wide job needs 50 calls. These take at least 150 s at 3 s apart, which is longer than a 120 s deadline. Without reuse or a partial answer, the job cannot finish.
- If provider latency grows from 1 s to 5 s, the one-call-at-a-time rule becomes the limit. The budget drops from 20 to 12 calls a minute.
- A cold cache means that merging is the only reuse at the start.
- Retries add load when the provider is already struggling.

Without admission control, the baseline already wastes about nine calls in ten under overload. This workload is where admission control, merging and the partial-answer gather each prove their worth, or fail.
