# Handoff: Sruthilaya

**Lane:** the job model, the subagent runner, the cache and merge, and the lead (plan fallback,
gather and brief). **Leads E2** (cache vs cache + merge) and **E3** (partial answer vs late answer,
simulator only). You built the prototype, so you own its move to deep research.

Read `CLAUDE.md` (shared rules) and `docs/contracts.md` §2, §3, §5 (what dispatch returns), §6, §8
to §11 and §12 before starting.

## What you produce for the others

| Thing | Contract section | Used by |
|---|---|---|
| Job model and the `WorkloadFile` JSON from `prototype/workload.py` | §12 | Muskan's harness (M6) and E1 (M9) |
| Fan-out, gather, completeness and the full §12 CSV columns in `prototype/system.py` | §6, §12 | E1 to E3 on the simulator; the simulator-vs-deployed check |
| `prototype/reuse.py`: modes `none`, `cache`, `cache_merge` | §8 merge protocol | E2 on the simulator |
| Runner `src/researchdesk/workflow/runner.py`: **`run_subagent`**, **`search_once`**, **`resume_step`** | §8 interfaces table | Muskan's worker calls `run_subagent`; Muskan's `POST /search` calls `search_once`; Satyaa's lease code calls `resume_step` |
| The Redis keys the runner writes: `rd:cache:{qkey}`, `rd:inflight:{qkey}`, `rd:waiters:{qkey}`, `rd:done:{qkey}`, `rd:job:{job_id}:sub:{subagent_id}` (with `stale_steps`), `rd:ckpt:{job_id}:{subagent_id}:{step}` | §8 | Satyaa's leases (checkpoints), Muskan's `GET /jobs/{job_id}` |
| The lead `src/researchdesk/workflow/lead.py`: **`plan`** and **`gather`** | §6, §8 interfaces | Muskan's Job API calls both; `GET /jobs/{job_id}` shows the result |
| Events `search.*` (only `search_once` emits them), `task.step_done`, `task.done`, `task.failed`, `job.gathered`, `job.finished`; counters `rd_searches_total`, `rd_merge_waiters_total`, `rd_stale_answers_total`, `rd_tasks_total` via `events.count`; job latency goes in `job.finished` | §10, §11 | Muskan's dashboard and live control room |

## What you need from the others

| Thing | From | Target | Until it lands |
|---|---|---|---|
| `events.emit` and `events.count` | Muskan (M7a) | Wed 11/25 | print the event's JSON line only |
| Versioned corpus in the simulator | Satyaa (T1) | Wed 11/25 | treat every result as version 0 |
| Gateway `POST /dispatch` (its result carries `request_id`) and the provider's `rd:corpus_version` | Satyaa (T4, T5) | Sun 11/29 | a fake gateway in tests that returns a result and a request id after a delay |
| Worker process and lease code | Muskan (M4), Satyaa (T7) | Wed 12/2, Sat 12/5 | call `run_subagent` directly in tests |
| Job API that calls your lead | Muskan (M3) | Sun 11/29 | call `plan` and `gather` directly in tests |
| Replay harness and Compose | Muskan (M6, M5) | Wed 12/2, Fri 11/27 | simulator results first |

## Your tasks, in order

| ID | Task | Files | Target | Done when |
|---|---|---|---|---|
| S1 | HW9 section 2 (recent progress: your commits and what each adds) and section 6 (preliminary results from `results/prototype/exp1_baseline_2026-11-22.csv`; a figure of briefs per minute against arrival rate, one line per worker count) | `prototype/plot_exp1.py`, shared draft | **Sun 11/22, 11:59 pm** | Text and figure in the shared draft |
| S6 | Review contract §8 (keys, merge protocol, checkpoints, the runner and lead functions) and §12; approve the PR | `docs/contracts.md` | Tue 11/24 | PR merged with all three approvals |
| S2 | Job model: a `Job` with N subagents. Each job draws one topic cluster of c distinct queries from the pool with the existing Zipf weights, and each subagent picks k distinct queries uniformly from that cluster (c ≥ k); `repeat_fraction_within` and `repeat_fraction_across`; `to_json` / `from_json` producing a contract `WorkloadFile` (`deadline_s` relative to arrival). Keep `make_workload` unchanged | `prototype/workload.py`, `tests/test_prototype_workload.py` | Wed 11/25 | Same seed gives the same jobs; a smaller c gives a higher within-job repeat fraction; the JSON passes `WorkloadFile.from_json` and round-trips exactly |
| S3 | Fan-out and gather in the simulator: worker slots take subagent tasks; `plan_time` and `synth_time` equal `RD_PLAN_MS` and `RD_SYNTH_MS` (2 s and 4 s by default; `synth_time` at most the gather margin); `gather` = `wait_all` or `deadline_partial(margin)`; a dropped search ends only its subagent `failed`; final status per contract §6 (the prototype's `rejected` becomes `failed`); `completeness` on `Outcome`; `summarize` produces every §12 CSV column, with `wasted_calls` as §12 defines it | `prototype/system.py`, `tests/test_prototype_system.py` | Fri 11/27 | `tests/test_prototype_baseline.py` still passes with one subagent per job; under `deadline_partial` a slowed subagent gives an `on_time` brief with completeness below 1; violations stay 0 |
| S4 | Cache and merge in the simulator (`prototype/reuse.py`): TTL and corpus version in the cache; in-flight table with waiters; **the merged deadline is the latest waiter's**; re-submit for waiters that can still make it after a drop; stale hits counted | `prototype/reuse.py`, `tests/test_prototype_reuse.py` | Sat 11/28 | Two subagents asking one key at once cause exactly 1 provider call; the first asker expiring does not cancel the call for a later waiter; a hit from an older corpus version is counted as stale |
| S5 | E2 and E3 runners on the simulator, seeds 0 to 2, a CSV in the §12 columns and one figure each | `prototype/exp2.py`, `prototype/exp3.py`, `results/prototype/` | Sun 11/29 | CSVs committed; violations 0 in every row |
| S7 | Runner in the service per §8, passing `user` from the task or request into every dispatch and event: `search_once` (query key → cache → in-flight claim `SET NX PX`, renewed while the dispatch is open, or wait on `rd:done:{qkey}` while polling the cache and the claim → `POST /dispatch` → write cache (with the result's `request_id`) → publish `ok` or `dropped` → staleness check against `rd:corpus_version`), `run_subagent` (from `resume_step`, checkpoint each step with `SET NX`, think time; the checkpoint and the `task.step_done` event carry `request_id`), `resume_step` | `src/researchdesk/workflow/runner.py` | Thu 12/3 | Compose integration test: 5 workers asking one key cause 1 provider call; a re-run of a finished task makes 0 provider calls |
| S8 | Lead: `plan` (a simple fallback split of the question into query lists) and `gather` (both policies; once the policy stops it waits `RD_SYNTH_MS`, then writes the final status, `completeness` and `finished_at_ms` in the job hash) | `src/researchdesk/workflow/lead.py` | Sat 12/5 | A job with one subagent slowed by a provider fault finishes `on_time` with completeness below 1 before its deadline; `plan` returns at least one `SubagentPlan` for any non-empty question |
| S9 | **E2** on Compose, then a few AWS points, compared with the simulator. E3 stays on the simulator | `experiments/e2/` | Sun 12/6 | A table of simulator vs deployed `briefs_per_min` with the percentage difference per point; any point more than 15% off (proposed tolerance) has a measured cause in the report |
| S10 | Report sections for E2 and E3, their poster panels, and a blog section | `docs/` | Wed 12/9 | In the shared draft |

## Watch-outs

- Pub/sub can lose messages: a waiter must also poll the cache, and must re-claim the key if the
  claim expires (`RD_INFLIGHT_LEASE_MS`) or the dispatch is dropped while its own deadline is ahead.
- Checkpoints use `SET NX`: the first write wins, so a reclaimed task re-running a step never
  overwrites a finished result.
- `RD_REUSE_MODE` must switch the same code between `none`, `cache` and `cache_merge`; E2 compares
  them on identical workloads.
- Use `query_key` from `researchdesk.contracts` in the services (a test checks it matches the
  prototype's).
- Never edit `results/prototype/exp1_baseline_2026-11-22.csv`. If a change is meant to alter E1,
  add a new dated baseline in the same PR and say why.

## Start here

1. Tonight: HW9 sections 2 and 6 (S1), from the frozen baseline CSV.
2. Review contract §8 and §12 (S6), then start S2 with tests first.
3. S3 and S4 need nothing from anyone else; stub the corpus version until Satyaa's T1 lands.
