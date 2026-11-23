# 7. Impact

**7. Impact.** Many agents share one rate limit, so calls are wasted and answers arrive late. Systems such as Anthropic's multi-agent research system start 3-5 subagents in parallel for one question (Section 4). Every search provider limits how fast it can be called. The preliminary simulator results show the problem (Section 6; simulator results, one subagent per job):

- With no reuse, throughput rose to 3.27 briefs a minute. It then collapsed to 0.27 when the load passed the provider ceiling. About nine in ten calls were wasted.
- When searches repeat, a cache lifted throughput from 1.67 to 4.37 briefs a minute. Provider calls fell from 591 to 82.

The significance reaches beyond search. Any system where many agents share a metered tool, such as a paid API or a rate-limited service, has the same three problems: a shared budget, duplicate calls and crashes. Research Desk measures how four parts change throughput, cost and recovery: a cache, merging, a paced gateway with admission control, and task leases. Operators get more finished jobs from the same budget. Users get answers on time and a fair share. Providers get fewer duplicate calls and no retry storms.

Classmates can use the project and help test it:

- **The live service.** The MCP server will run as a public service. A classmate will add its address as a custom connector in Claude Desktop, or with `claude mcp add` in Claude Code, and ask a research question. A handle in the address will identify each person. Per-user quotas will stop one person from using the whole budget. The service will be live only while an AWS Learner Lab session runs, not around the clock.
- **The replay harness.** A classmate will run their own workload file against the system, or against their own rate-limited service, and compare the results. The live control room will show the load and the provider's violation count during the run.
