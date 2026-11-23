# Research Desk: instructions for every Claude Code session

Research Desk is the BSDS (CS6650) final project of Sruthilaya, Satyaa and Muskan: a backend that
runs **deep-research jobs** (one question, N parallel subagent tasks, each running k paper searches)
under **one shared provider budget** modelled on arXiv: one call in flight, call starts at least 3 s
apart, so at most 20 calls a minute for the whole system. The fixes we build and measure: a shared
cache, merging identical in-flight searches, one paced gateway with admission control, a
deadline-aware gather, and task leases that resume a crashed subagent from its last step.

## Read these first, in this order

1. `docs/handoff/<your name>.md`: your tasks, what you produce, what you consume, and what the
   other two are building. Start every session here.
2. `docs/contracts.md` and `src/researchdesk/contracts.py`: every endpoint, message, Redis key,
   event, metric and setting. These win over anything else.
3. `docs/PLAN.md` and the experiment list in `README.md` are the **v1 draft and are superseded**.
   Do not follow their experiment numbering or the support-style scenario.

## Two modes, one server

- **Mode A (measured):** the replay harness posts scripted jobs to the Job API. **Every number in
  the report comes from Mode A**, with `client` = `harness`.
- **Mode B (demo only):** Claude Code subagents (the Code tab of the Claude Desktop app) call the
  MCP tool `search_papers`. Never run it during a measured run: real agents are not repeatable.
- **It is a live, public service:** anyone's Claude Desktop (Chat tab, Mode A) or Claude Code (Mode
  B) adds `https://TUNNEL-HOST/mcp/u/HANDLE`. A Cloudflare quick tunnel on the AWS stack gives the
  address; per-user quotas protect the shared budget; there is no login. It is up while a lab
  session runs.
- The MCP server is a thin wrapper over the Job API. The measured path never goes through MCP.

## Rules

1. **Use the contract, never retype it.** Import names from `researchdesk.contracts`. A contract
   change is one PR that edits `docs/contracts.md`, `contracts.py` and `tests/test_contracts.py`
   together and is approved by all three owners.
2. **Tests first, and the suite stays green.** Run `python -m pytest -q` before every PR. A PR may
   add tests but never leave one failing, and never deletes or skips a test to make the suite pass.
3. **Stay in your lane.** Edit the files your handoff names. If you need something from another
   lane, stub it behind the contract (same names and shapes) and open an issue for the owner.
   Never change the contract to suit a stub.
4. **The provider's violation counters must read 0 in every run.** A non-zero count is a bug to
   fix, not a result to report.
5. **Every request, event and metric carries `client` and `run_id`.**
6. **Time:** a name ending in `_ms` is a simulated duration or deadline; a name ending in
   `_at_ms`, and `ts_ms`, is an absolute real time on the shared clock, Redis `TIME`. Multiply a
   simulated duration by `RD_TIME_SCALE` only to sleep or wait. Over HTTP, deadlines are remaining
   time. Only the gateway paces provider calls. Details: `docs/contracts.md` §2.
7. **Every state change emits one event** (`EventRecord`), to the log and to `rd:events`. The live
   control room shows only what services emit, so a missing event is a missing feature.
8. **Keep `prototype/` working.** With one subagent per job, the simulator must still reproduce the
   old Experiment 1 results (`python prototype/exp1.py`).
9. **Do not guess library APIs.** Check the official docs for the MCP Python SDK, Redis, FastAPI
   and the Prometheus client before using them. Add a dependency to `pyproject.toml` in the same
   PR, with one line on why.
10. **One GitHub issue per task** (use the task template), one branch per task named
    `name/short-topic`, and every PR reviewed by one other teammate before merging.
11. **Record decisions and problems** in `docs/project-management/LOG.md` (date, decision, who).

## Commands

```bash
python -m pip install pytest      # until task M1 adds a dev extra
python -m pytest -q               # all tests
python prototype/exp1.py          # Experiment 1 on the simulator, writes results/prototype/
```

## Dates (EST)

Targets, not gates: build finished and every experiment run by **Sun 12/6**; every deliverable
ready by **Fri 12/11**. Fixed: final deliverables **Mon 12/14, 12:00 pm**; presentations
**Mon 12/14, 4–6 pm** (syllabus: 9 am and 1–3 pm Pacific).
