# Research Desk

Backend for an AI research assistant. It answers more student questions on time under a fixed paper-search API budget by **sharing search results** (cache) and **merging identical in-flight searches**.

> Northeastern BSDS final project. Team: Sruthilaya Umasankari Soma Shanmuga Sundaram, Satyaa Sudarshan Guruswamy Sethuraman, Muskan Jain.

> **Current design (v2, 2026-11-22, pending team approval):** start at `docs/handoff/README.md`
> and `docs/contracts.md`. The experiment list and ownership table below are the v1 draft.

## Why
One research question triggers several searches. Many concurrent users means many agents competing for the same paper-search budget (modeled on arXiv: 1 in-flight call, 3 s pacing, at most 20 calls/min). Duplicate searches waste that budget.

## Architecture (planned)
- **Workers** run agent search workflows and assemble briefs (`src/researchdesk/workflow`)
- **Shared cache + in-flight merge** coordinated through shared state
- **Paced gateway** with bounded queue and deadline checks before dispatch (`src/researchdesk/gateway`)
- **Simulated paper-search API** that enforces and records pacing/overlap violations (`src/researchdesk/simulator`)
- **Workflow API, replay harness, metrics** (`src/researchdesk/api`, `harness`, `src/researchdesk/metrics`)

## Experiments
1. Scaling ceiling: workers vs. fixed provider budget (no reuse)
2. Benefit/limits of reuse: none vs. cache vs. cache + merge
3. (Optional) Gateway failover

Primary metric: correct briefs completed before deadline per minute.

## Repo layout
| Path | Purpose |
|---|---|
| `src/researchdesk/` | service code |
| `harness/` | traffic replay + experiment runner |
| `experiments/` | per-experiment configs and analysis scripts |
| `results/` | curated results and figures |
| `docs/project-management/` | planning, decisions, progress log |
| `tests/` | unit/integration tests |

## Getting started
```bash
docker compose up   # once services are implemented
pip install -e .
pytest
```

## Ownership
| Area | Owner |
|---|---|
| Workflow, brief assembly, query identity, cache, in-flight merge, Exp 2 | Sruthilaya |
| Gateway, bounded queue, deadlines, simulator checks, failover (Exp 3) | Satyaa |
| API, worker deployment, replay harness, metrics, demo UI, Exp 1 | Muskan |
