# 3. Objectives

**3a. Short-term and long-term objectives.** The short-term objectives are due with the final deliverables on Mon 12/14. The target for the build and for every experiment run is Sun 12/6.

- Run the system as services around one Redis store (a fast in-memory database), on Docker Compose and on a few AWS machines. The services are the job API, workers, gateway, provider simulator, MCP server and live control room.
- Show one question that becomes a job. Its subagent tasks run in parallel, and the job returns a brief with its completeness.
- Run experiments E1, E2 and E4 on the simulator and on the deployed system (a few points each) with three seeds. Run E3 on the simulator only.
- Keep the provider simulator's violation counters at zero in every run. Show that a job still returns a brief when a worker is killed in the middle of it. Log the recovery time.
- Deliver the code repository, report, poster, blog post and presentation.

The long-term vision goes beyond the course:

- Real language-model agents replace the scripted ones, and several providers with their own limits replace the one simulated provider.
- The gateway becomes highly available. Failover uses a fencing token (a number that lets the provider refuse an old gateway). A consensus protocol such as Raft or Paxos is added if the gateway must never stall.
- Fair sharing between wide and narrow jobs (experiment E5), per-tenant budgets and billing follow. A real sign-in (OAuth 2.1) replaces the handle that identifies a user today.
- The gateway becomes a reusable library for any rate-limited agent tool.

**3b. Observability, performance, reliability and cost control.** The product serves AI agents. The people who deploy it must know how it performs, how it fails and what it costs. Observability is part of the design (Section 5):

- Every state change will be a structured event.
- Prometheus counters will feed a Grafana dashboard.
- A live control room will show the events as they arrive.
- The provider simulator's violation count must be zero in every run.

Five controls protect performance, reliability and cost:

- **Admission control** rejects a job that cannot finish before its deadline, so the job spends no calls. The preliminary runs show why. With no admission control, about nine in ten provider calls were wasted under overload (Section 6).
- **The cache and merging of identical searches** cut provider calls. On a workload of repeated searches, calls fell from 591 to 82 in the simulator (Section 6).
- **Deadline drops** stop the system from paying for an answer that would arrive late.
- **Per-user quotas** stop one user from taking the whole shared budget.
- **Crash recovery** restarts a subagent without repeating a finished step. A crash does not double the cost of a job.

Performance is measured as correct briefs on time per minute and 95th-percentile latency. Reliability is measured as recovery time and violations. Cost is measured as provider calls per brief and wasted calls. Language-model token cost is not measured, because the backend calls no model. A per-job cap on tokens is future work.
