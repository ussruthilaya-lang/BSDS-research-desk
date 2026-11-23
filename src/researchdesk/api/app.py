"""Job API (contract section 6): POST /jobs, GET /jobs/{id}, GET /jobs/{id}/trace, POST /search,
GET /metrics, GET /health."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable

import httpx
import redis
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse

from researchdesk import contracts as c
from researchdesk.api import stubs
from researchdesk.metrics import events


def _default_admit(settings: c.Settings, req: c.AdmitRequest) -> c.AdmitResult:
    try:
        r = httpx.post(f"{settings.gateway_url}/admit", json=req.to_dict(), timeout=5)
        r.raise_for_status()
        return c.AdmitResult.from_dict(r.json())
    except (httpx.HTTPError, ValueError) as err:
        raise HTTPException(503, f"gateway unavailable: {err}")


@dataclass
class Deps:
    """The cross-lane calls. Any left None falls back to the real module, then to a stub."""
    admit: Callable | None = None   # (settings, AdmitRequest) -> AdmitResult
    plan: Callable | None = None    # (settings, question) -> list[SubagentPlan]
    gather: Callable | None = None  # (settings, job_id) -> None
    search: Callable | None = None  # (settings, SearchRequest, trace_id) -> SearchResult


def _resolve(deps: Deps) -> Deps:
    try:
        from researchdesk.workflow import lead  # noqa: F401  (Sruthilaya, S8)
        lead_plan, lead_gather = lead.plan, lead.gather
    except (ImportError, AttributeError):
        lead_plan, lead_gather = stubs.plan, stubs.gather
    try:
        from researchdesk.workflow import runner  # noqa: F401  (Sruthilaya, S7)

        def run_search(settings, req, trace_id):
            return runner.search_once(settings, req.query, req.deadline_ms, req.client, req.run_id, trace_id)
    except (ImportError, AttributeError):
        run_search = stubs.search
    return Deps(deps.admit or _default_admit, deps.plan or lead_plan, deps.gather or lead_gather,
                deps.search or run_search)


def _bad(message: str):
    raise HTTPException(400, message)


def _validate(req: c.JobRequest) -> None:
    if req.client not in {x.value for x in c.Client}:
        _bad(f"unknown client {req.client!r}")
    if not c.valid_user(req.user):
        _bad("user must match [a-z0-9-]{1,32}")
    if req.deadline_ms <= 0:
        _bad("deadline_ms must be positive")
    if req.gather is not None and req.gather not in {x.value for x in c.GatherPolicy}:
        _bad(f"unknown gather policy {req.gather!r}")
    if req.plan is not None and (not req.plan or any(not p.queries for p in req.plan)):
        _bad("plan needs at least one subagent, each with at least one query")


def _sleep_sim(settings: c.Settings, sim_ms: float) -> None:
    time.sleep(c.to_real_ms(sim_ms, settings.time_scale) / 1000)


def create_app(settings: c.Settings, deps: Deps | None = None) -> FastAPI:
    app = FastAPI(title="researchdesk-api")
    app.state.settings = settings
    d = _resolve(deps or Deps())

    def rds() -> redis.Redis:
        return events.client(settings)

    def now_ms() -> int:
        return c.redis_time_to_ms(rds().time())

    def emit(name: str, run_id: str, client: str, user: str, job_id: str = "", **fields) -> None:
        events.emit(settings, c.EventRecord(
            ts_ms=now_ms(), run_id=run_id, client=client, service="api", event=name,
            trace_id=job_id, job_id=job_id, user=user, fields=fields))

    @app.exception_handler(RequestValidationError)
    def _validation(_: Request, exc: RequestValidationError):
        return JSONResponse({"detail": "invalid request"}, status_code=400)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "api", "contract_version": c.CONTRACT_VERSION}

    @app.post("/jobs", status_code=202)
    def post_job(payload: dict = Body(...)):
        try:
            req = c.JobRequest.from_dict(payload)
        except ValueError as err:
            _bad(str(err))
        _validate(req)
        r = rds()
        job_id = req.job_id or uuid.uuid4().hex[:12]
        created = now_ms()
        gather = req.gather or settings.gather_policy
        deadline_at = created + int(c.to_real_ms(req.deadline_ms, settings.time_scale))
        # HSETNX makes the duplicate check atomic: only one request can claim a job_id
        if not r.hsetnx(c.job_key(job_id), "status", c.JobStatus.ADMITTED.value):
            raise HTTPException(409, f"job_id {job_id!r} already exists")
        ctx = (req.run_id, req.client, req.user, job_id)
        emit(c.EventName.JOB_SUBMITTED.value, *ctx, deadline_ms=req.deadline_ms)

        plan = req.plan if req.plan is not None else d.plan(settings, req.question)
        _sleep_sim(settings, settings.plan_ms)  # planning time counts against the deadline
        n, k = len(plan), max(len(p.queries) for p in plan)
        emit(c.EventName.JOB_PLANNED.value, *ctx, n_subagents=n, k=k)
        events.count(settings, "rd_jobs_total", {"status": c.JobStatus.ADMITTED.value})

        job = {"n_subagents": n, "done": 0, "failed": 0, "completeness": 0, "created_at_ms": created,
               "deadline_at_ms": deadline_at, "gather": gather, "client": req.client,
               "user": req.user, "run_id": req.run_id}
        if settings.admission:
            verdict = d.admit(settings, c.AdmitRequest(
                job_id=job_id, n_subagents=n, k=k, deadline_ms=max(req.deadline_ms - settings.plan_ms, 0),
                expected_hit_rate=0.0, user=req.user))
            if not verdict.admitted:
                r.hset(c.job_key(job_id), mapping={**job, "status": c.JobStatus.REJECTED.value,
                                                   "finished_at_ms": now_ms()})
                emit(c.EventName.JOB_REJECTED.value, *ctx, reason=verdict.reason)
                events.count(settings, "rd_jobs_total", {"status": c.JobStatus.REJECTED.value})
                return c.JobAccepted(job_id, job_id, c.JobStatus.REJECTED.value).to_dict()
            emit(c.EventName.JOB_ADMITTED.value, *ctx, estimated_ms=verdict.estimated_ms)
        else:
            emit(c.EventName.JOB_ADMITTED.value, *ctx, estimated_ms=0)

        r.hset(c.job_key(job_id), mapping=job)
        try:
            r.xgroup_create(c.TASK_STREAM, c.TASK_GROUP, id="0", mkstream=True)
        except redis.ResponseError as err:
            if "BUSYGROUP" not in str(err):
                raise
        for p in plan:
            r.hset(c.subagent_key(job_id, p.subagent_id), mapping={
                "status": c.TaskStatus.QUEUED.value, "steps_done": 0, "k": len(p.queries),
                "stale_steps": 0, "worker_id": ""})
            r.xadd(c.TASK_STREAM, {
                "job_id": job_id, "subagent_id": p.subagent_id, "queries": json.dumps(p.queries),
                "deadline_at_ms": deadline_at, "trace_id": job_id, "client": req.client,
                "user": req.user, "run_id": req.run_id, "attempt": 0})
            emit(c.EventName.TASK_ENQUEUED.value, *ctx, queries=p.queries, subagent_id=p.subagent_id)

        def run_gather():
            try:
                d.gather(settings, job_id)
            except Exception as err:  # a crashed gather would leave the job running forever
                print(f"gather failed for {job_id}: {err!r}", file=sys.stderr, flush=True)

        threading.Thread(target=run_gather, daemon=True).start()
        return c.JobAccepted(job_id, job_id, c.JobStatus.ADMITTED.value).to_dict()

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str):
        r = rds()
        job = r.hgetall(c.job_key(job_id))
        if not job:
            raise HTTPException(404, "unknown job")
        subs = []
        for i in range(int(job["n_subagents"])):
            s = r.hgetall(c.subagent_key(job_id, i))
            if not s:  # a rejected job has no tasks
                continue
            steps = int(s["steps_done"])
            papers = []
            for step in range(steps):
                ckpt = r.get(c.checkpoint_key(job_id, i, step))
                papers.append(json.loads(ckpt)["paper_ids"] if ckpt else [])
            subs.append(c.SubagentView(i, s["status"], steps, int(s["k"]), papers, int(s["stale_steps"])))
        finished = job.get("finished_at_ms")
        return c.JobView(job_id, job["status"], float(job["completeness"]), int(job["n_subagents"]), subs,
                         int(job["created_at_ms"]), int(finished) if finished else None).to_dict()

    @app.get("/jobs/{job_id}/trace")
    def get_trace(job_id: str):
        if not rds().exists(c.job_key(job_id)):
            raise HTTPException(404, "unknown job")
        out = []
        for _id, f in rds().xrange(c.EVENT_STREAM):
            rec = json.loads(f[c.EVENT_FIELD])
            if rec["trace_id"] == job_id:
                out.append(rec)
        return out

    @app.post("/search")
    def post_search(payload: dict = Body(...)):
        try:
            req = c.SearchRequest.from_dict(payload)
        except ValueError as err:
            _bad(str(err))
        if req.client not in {x.value for x in c.Client} or not c.valid_user(req.user) or req.deadline_ms <= 0:
            _bad("invalid search request")
        res = d.search(settings, req, uuid.uuid4().hex[:12])
        code = 200 if res.status == "ok" else 429 if res.reason == c.DropReason.USER_QUOTA.value else 503
        return JSONResponse(res.to_dict(), status_code=code)

    @app.get("/metrics")
    def get_metrics(run_id: str | None = None):
        run = run_id or settings.run_id
        lines, seen = [], set()
        for field, value in sorted(rds().hgetall(c.metrics_key(run)).items()):
            name, _, labels = field.partition("{")
            if name not in seen and name in c.METRICS:
                lines.append(f"# TYPE {name} {c.METRICS[name][0]}")
                seen.add(name)
            lines.append(f'{name}{{run_id="{run}"' + ("," + labels if labels else "}") + f" {value}")
        return PlainTextResponse("\n".join(lines) + "\n")

    return app


app = create_app(c.Settings.from_env(os.environ))
