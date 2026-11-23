# HW9 section 4: sources log

Every outside claim in `sections/04-related-work.md`, with the page, the date it was read, and the
exact words relied on. All pages were read on **2026-11-22**. `tests/test_hw9.py` fails if section 4
cites a URL that is not listed here. Re-read a page before changing a claim that depends on it.

## Anthropic: How we built our multi-agent research system

URL: https://www.anthropic.com/engineering/multi-agent-research-system (shown as published Jun 13, 2025)

- "the lead agent spins up 3-5 subagents in parallel rather than serially"
- "direct comparisons might need 2-4 subagents with 10-15 calls each, and complex research might use more than 10 subagents"
- "performed the exact same searches as other agents"
- "Agents are stateful and errors compound."
- "we built systems that can resume from where the agent was when the errors occurred"
- "Synchronous execution creates bottlenecks. Currently, our lead agents execute subagents synchronously, waiting for each set of subagents to complete before proceeding."
- Not found: a search of the page text (26,785 characters) for "rate limit" gave no match. Section 4 says only that the text read contains no mention of rate limits.

## arXiv: API terms of use

URL: https://info.arxiv.org/help/api/tou.html

- "When using the legacy APIs (including OAI-PMH, RSS, and the arXiv API), make no more than one request every three seconds, and limit requests to a single connection at a time. These limits may change in the future."
- "the following rate limits apply to all of the machines under your control as a whole. You should not attempt to overcome these limits by increasing the number of machines used to make requests."

## Go: package singleflight

URL: https://pkg.go.dev/golang.org/x/sync/singleflight

- "Package singleflight provides a duplicate function call suppression mechanism."
- Its index lists `func (g *Group) Do(key string, fn func() (any, error)) (v any, err error, shared bool)`, so calls are grouped by a key.

## The Tail at Scale

URL: https://research.google/pubs/the-tail-at-scale/ (Jeffrey Dean and Luiz André Barroso, Communications of the ACM, 56 (2013), pp. 74-80)

Only the abstract page was read, not the paper.

- "It is challenging to keep the tail of the latency distribution low for interactive services as the size and complexity of the system scales up or as overall utilization increases."
- "Temporary high latency episodes which are unimportant in moderate size systems may come to dominate overall service performance at large scale."
- "...large online services need to create a predictably responsive whole out of less predict[able parts]" (the page text was cut at this point in the read)

## Model Context Protocol: architecture overview

URL: https://modelcontextprotocol.io/docs/2026-07-28/learn/architecture.md

- "Local MCP servers that use the STDIO transport typically serve a single MCP client, whereas remote MCP servers that use the Streamable HTTP transport will typically serve many MCP clients."

## Course readings (not on the web; checked in the BSDS vault)

- Dean and Ghemawat, MapReduce, Communications of the ACM, 2008 (HW2 Part I). The vault page `bsds/wiki/concepts/mapreduce.md`, section "Fault tolerance", built from the course PDF: any map task a failed worker completed is reset to idle and re-run, because its output lives only on that worker's local disk; a completed reduce task is not re-run, because its output was written to the distributed file system.
- Lamport, Time, Clocks, and the Ordering of Events in a Distributed System, Communications of the ACM, July 1978, pp. 558-565 (HW3 Part I). Vault page `bsds/wiki/concepts/logical clocks and happened-before.md`: "happened before" is the order events have for certain.
- Takada, Distributed Systems for Fun and Profit (recommended text). Vault page `bsds/wiki/concepts/system model.md`: the failure model; most real systems assume crash-recovery, where a node fails only by crashing and may come back later.
