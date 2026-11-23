# 7. Impact

**7. Impact.** Systems such as Anthropic's multi-agent research system start 3-5 subagents in parallel for a single question (Section 4), and every search provider limits how fast it can be called. When many agents share one limit, calls are wasted and answers arrive late. The preliminary simulator results make the problem concrete. With no reuse, throughput rose to 3.27 briefs a minute and then collapsed to 0.27 as the load passed the provider ceiling, and about nine in ten calls were wasted. When searches repeat, a cache lifted throughput from 1.67 to 4.37 briefs a minute while provider calls fell from 591 to 82 (Section 6; simulator results, one subagent per job).

The significance reaches beyond search. Any system where many agents share a metered tool, such as a paid API or a rate-limited service, faces the same budget, duplicate-call and crash problems, and Research Desk measures how a cache, merging, a paced gateway with admission control, and task leases change throughput, cost and recovery. Operators get more finished jobs from the same budget, users get answers on time and a fair share, and providers get fewer duplicate calls and no retry storms.

Classmates can use the project and help test it:

- **The live service.** The MCP server will run as a public service. A classmate will be able to add its address as a custom connector in Claude Desktop, or with `claude mcp add` in Claude Code, and ask a research question. A handle in the address will identify each person, and per-user quotas will keep one person from using the whole budget. The service will be live while an AWS Learner Lab session runs, so it will be available for testing and the demonstration and not around the clock.
- **The replay harness.** A classmate will be able to run their own workload file against the system, or against their own rate-limited service, and compare the results. The live control room will show the load and the provider's violation count while it runs.
