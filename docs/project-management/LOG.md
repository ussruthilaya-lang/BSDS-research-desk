# Project management log

Kept in-repo so the project-management writeup (due 12/14) can be assembled from real history.

| Date | Decision / event | Who |
|---|---|---|
| 2026-11-19 | Repo created | team |
| 2026-11-22 | Proposed (pending team approval): headline scenario is deep research, one question becoming N parallel subagent tasks under one arXiv-like budget. Replaces the support-style flow in `docs/PLAN.md` v1 | Satyaa |
| 2026-11-22 | Language: Python. Satyaa reports the course allows any programming language (source not recorded here; add it) | Satyaa |
| 2026-11-22 | Proposed: E1, E2, E4 core; E3 simulator only; E5, E6 future work. Mode A (scripted harness) for every measured number, Mode B (Claude Code subagents over MCP) for the demo only | Satyaa |
| 2026-11-22 | Proposed owners: MCP server and demo, Satyaa (T12, T13); live control room, Muskan (M12); old demo page (M10) dropped | Satyaa |
| 2026-11-22 | Proposed: no internal checkpoints. Targets: build and experiments by Sun 12/6, deliverables ready Fri 12/11; due Mon 12/14 12:00 pm EST | Satyaa |
| 2026-11-22 | Contract v1 drafted (`docs/contracts.md`, `src/researchdesk/contracts.py`, `tests/test_contracts.py`) and handoff files (`docs/handoff/`, checked by `tests/test_handoff.py`), for review in one PR (S6, T3, M2) | Satyaa |
| 2026-11-22 | Frozen Experiment 1 baseline `results/prototype/exp1_baseline_2026-11-22.csv` (matches the 2026-11-21 run: 4 workers at 12 arrivals a minute gives 0.27 briefs a minute), guarded by `tests/test_prototype_baseline.py` | Satyaa |
| 2026-11-22 | Handoff tested by three dry-run Claude sessions, one per person; their findings were fixed before review | Satyaa |
| 2026-11-22 | Proposed: the MCP server is a live public service. A Cloudflare quick tunnel on the AWS stack gives an `https://` address any Claude Desktop or Claude Code can add (`/mcp/u/HANDLE`); per-user quotas, no login (OAuth is future work); live on demand while a lab session runs | Satyaa |
| 2026-11-22 | Contract v1.1 proposed (additive, no service exists yet, so `CONTRACT_VERSION` stays 1): the provider writes `rd:corpus_version` so staleness is not under-counted when the cache absorbs calls; `request_id` carried from provider call to cache entry, checkpoint and `task.step_done` so `wasted_calls` is computable; `complete_briefs_per_min` column so E3 cannot be won by partial briefs alone; `RD_PLAN_MS` and `RD_SYNTH_MS` so the simulator and the deployed lead take equal time; merge protocol clarifications (waiter cleanup, deadline conversion, fixed dispatch deadline) | Sruthilaya |
| 2026-11-23 | HW9 sections 1, 4 and 5 (build tool `python docs/hw9/build.py`, sources log) and Sruthilaya's sections 2 and 6 are merged in `docs/hw9/sections/`. `python docs/hw9/build.py --check` still lists the open items: the background lines of Sruthilaya and Muskan in section 1, and sections 3, 7, 8, 9 and 10 | Satyaa |

Use GitHub Issues + a Project board for tasks; record design pivots and problems here.
