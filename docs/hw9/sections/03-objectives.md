# 3. Objectives

**3a. Short-term and long-term objectives.** The short-term objectives are due with the final deliverables on Mon 12/14, with a target of Sun 12/6 for the build and every experiment run:

- Run the system as services around one Redis store, on Docker Compose and on a few AWS machines: the job API, workers, gateway, provider simulator, MCP server and live control room.
- Show one question becoming a job whose subagent tasks run in parallel, and a brief returned with its completeness.
- Run experiments E1, E2 and E4 on the simulator and on the deployed system (a few points each) with three seeds, and E3 on the simulator.
- Keep the provider simulator's violation counters at zero in every run, and show that killing a worker mid-job still produces a brief, with the recovery time logged.
- Deliver the code repository, report, poster, blog post and presentation.

The long-term vision goes beyond the course. Real language-model agents would replace the scripted ones, and would be measured under the same limits. Several providers, each with its own limits, would replace the single simulated one. The gateway would become highly available, with failover guarded by a fencing token and, if it must never stall, a consensus protocol such as Raft or Paxos. Fair sharing between wide and narrow jobs (experiment E5) and per-tenant budgets and billing would follow, with a real sign-in (OAuth 2.1) in place of the handle that identifies a user today. The gateway could be released as a reusable library for any rate-limited agent tool.

**3b. Observability, performance, reliability and cost control.** The product serves AI agents, so the people who deploy it need to know how it performs, how it fails and what it costs. Observability is part of the design (Section 5): every state change will be a structured event, Prometheus counters will feed a Grafana dashboard, a live control room will show the events as they arrive, and the provider simulator's violation count must be zero in every run.

The design has five controls that protect performance, reliability and cost for a deployer:

- **Admission control** rejects a job that cannot finish before its deadline, so it spends no calls. The preliminary runs show why: with no admission control, about nine in ten provider calls were wasted under overload (Section 6).
- **The cache and merging of identical searches** cut provider calls. On a workload of repeated searches, calls fell from 591 to 82 in the simulator (Section 6).
- **Deadline drops** stop the system from paying for an answer that would arrive late.
- **Per-user quotas** keep one user from taking the whole shared budget.
- **Crash recovery** means a restarted subagent repeats no finished step, so a crash does not double the cost of a job.

Performance is measured as correct briefs on time per minute and 95th-percentile latency, reliability as recovery time and violations, and cost as provider calls per brief and wasted calls. The cost of language-model tokens is not measured, because the backend calls no model. A per-job cap on tokens is future work.
