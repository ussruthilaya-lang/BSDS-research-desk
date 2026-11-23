"""Keeps src/researchdesk/contracts.py and docs/contracts.md in sync, and checks the shared helpers."""
import re
from dataclasses import fields
from pathlib import Path

import pytest

from researchdesk import contracts as c

DOC = (Path(__file__).resolve().parents[1] / "docs" / "contracts.md").read_text()
TICKED = set(re.findall(r"`([^`]+)`", DOC))

WIRE_CLASSES = [
    c.SubagentPlan, c.JobRequest, c.JobAccepted, c.SubagentView, c.JobView, c.SearchRequest,
    c.SearchResult, c.DispatchRequest, c.DispatchResult, c.AdmitRequest, c.AdmitResult,
    c.ProviderSearchRequest, c.ProviderSearchResult, c.FaultPlan, c.ProviderStats,
    c.WorkloadJob, c.WorkloadFile, c.EventRecord,
]
ENUMS = [c.Client, c.DropReason, c.JobStatus, c.TaskStatus, c.SearchSource, c.ReuseMode,
         c.GatherPolicy, c.QueuePolicy, c.EventName]


def section(title_prefix: str) -> str:
    """Text of the doc section whose heading starts with title_prefix, up to the next '## '."""
    start = DOC.index(f"## {title_prefix}")
    end = DOC.find("\n## ", start + 3)
    return DOC[start:end if end != -1 else None]


# ------------------------------------------------------------ helpers ------

def test_query_key_matches_prototype():
    from sim import query_key as prototype_query_key  # prototype/ is on sys.path via conftest

    for q in ["Distributed Caching!", "caching distributed", "  Raft  raft consensus ", "", "GPU-v2 x86"]:
        assert c.query_key(q) == prototype_query_key(q)


def test_time_helpers():
    assert c.to_real_ms(3000, 0.1) == pytest.approx(300)
    assert c.to_sim_ms(300, 0.1) == pytest.approx(3000)
    assert c.redis_time_to_ms([b"1700000000", b"123456"]) == 1_700_000_000_123


def test_redis_keys():
    assert c.cache_key("a b") == "rd:cache:a b"
    assert c.inflight_key("k") == "rd:inflight:k"
    assert c.waiters_key("k") == "rd:waiters:k"
    assert c.done_channel("k") == "rd:done:k"
    assert c.job_key("j1") == "rd:job:j1"
    assert c.subagent_key("j1", 2) == "rd:job:j1:sub:2"
    assert c.checkpoint_key("j1", 2, 3) == "rd:ckpt:j1:2:3"
    assert c.heartbeat_key("w1") == "rd:hb:w1"
    assert c.metrics_key("r1") == "rd:metrics:r1"
    assert c.CORPUS_VERSION_KEY == "rd:corpus_version"


def test_enum_values_unique_and_event_names_well_formed():
    for enum in ENUMS:
        values = [e.value for e in enum]
        assert len(values) == len(set(values)), enum.__name__
    for e in c.EventName:
        assert re.fullmatch(r"[a-z]+\.[a-z_]+", e.value), e.value


# ------------------------------------------------------- wire messages -----

def test_job_request_round_trip_with_nested_plan():
    req = c.JobRequest(
        question="q", deadline_ms=120_000, client="harness", run_id="r1",
        plan=[c.SubagentPlan(0, ["topic 1", "topic 2"]), c.SubagentPlan(1, ["topic 3"])],
    )
    back = c.JobRequest.from_json(req.to_json())
    assert back == req
    assert isinstance(back.plan[0], c.SubagentPlan)


def test_workload_file_round_trip():
    wf = c.WorkloadFile(version=1, seed=7, params={"n": 3, "k": 2}, jobs=[
        c.WorkloadJob("j0", 1.5, 120.0, [c.SubagentPlan(0, ["a", "b"])]),
    ])
    assert c.WorkloadFile.from_json(wf.to_json()) == wf


def test_decode_rejects_unknown_and_missing_fields():
    with pytest.raises(ValueError):
        c.SearchRequest.from_dict({"query": "q", "deadline_ms": 1, "client": "test", "run_id": "r", "extra": 1})
    with pytest.raises(ValueError):
        c.SearchRequest.from_dict({"query": "q"})


def test_event_record_validates_names():
    ev = c.EventRecord(ts_ms=1, run_id="r", client="harness", service="api", event="job.submitted",
                       job_id="j1", fields={"n_subagents": 3})
    assert c.EventRecord.from_json(ev.to_json()) == ev
    with pytest.raises(ValueError):
        c.EventRecord(ts_ms=1, run_id="r", client="harness", service="api", event="job.exploded")
    with pytest.raises(ValueError):
        c.EventRecord(ts_ms=1, run_id="r", client="robot", service="api", event="job.submitted")


# ------------------------------------------------------------ settings -----

def test_settings_defaults_and_env_overrides():
    s = c.Settings.from_env({})
    assert s == c.Settings()
    s = c.Settings.from_env({"RD_TIME_SCALE": "0.1", "RD_QUEUE_MAX": "20", "RD_ADMISSION": "off",
                             "RD_REUSE_MODE": "none"})
    assert (s.time_scale, s.queue_max, s.admission, s.reuse_mode) == (0.1, 20, False, "none")


@pytest.mark.parametrize("env", [
    {"RD_REUSE_MODE": "everything"}, {"RD_ADMISSION": "maybe"}, {"RD_TIME_SCALE": "0"},
    {"RD_GATHER_POLICY": "whenever"}, {"RD_QUEUE_POLICY": "lifo"},
])
def test_settings_reject_bad_values(env):
    with pytest.raises(ValueError):
        c.Settings.from_env(env)


def test_every_setting_has_one_env_var():
    assert {f.name for f in fields(c.Settings)} == set(c.ENV_VARS)


# ------------------------------------------------- doc and code in sync -----

def test_doc_names_contract_version():
    assert f"(version {c.CONTRACT_VERSION})" in DOC.splitlines()[0]


def test_every_enum_value_is_in_doc():
    missing = [e.value for enum in ENUMS for e in enum if e.value not in TICKED]
    assert not missing, f"add to docs/contracts.md: {missing}"


def test_events_section_and_code_agree():
    sec = section("10. Event names")
    in_doc = set(re.findall(r"`([a-z]+\.[a-z_]+)`", sec))
    in_code = {e.value for e in c.EventName}
    assert in_doc == in_code, f"doc only: {in_doc - in_code}; code only: {in_code - in_doc}"


def test_env_vars_agree():
    in_doc = set(re.findall(r"`(RD_[A-Z_]+)`", DOC))
    assert in_doc == set(c.ENV_VARS.values())


def test_settings_table_defaults_match_code():
    defaults = c.Settings()
    for name, env in c.ENV_VARS.items():
        row = re.search(rf"^\| `{env}` \| ([^|]+) \|", DOC, re.M)
        assert row, f"no settings row for {env}"
        doc_default = row.group(1).strip()
        value = getattr(defaults, name)
        expected = ("on" if value else "off") if isinstance(value, bool) else (str(value) or "(empty)")
        assert doc_default == expected, f"{env}: doc says {doc_default}, code says {expected}"


def test_endpoints_and_ports_in_doc():
    for service, endpoints in c.ENDPOINTS.items():
        for ep in endpoints:
            assert ep in TICKED, f"{service}: {ep}"
    services = section("1. Services")
    for port in c.PORTS.values():
        assert f"| {port} |" in services


def test_metrics_agree():
    in_doc = set(re.findall(r"`(rd_[a-z_]+)`", DOC))
    assert in_doc == set(c.METRICS)
    sec = section("11. Metrics")
    for name, (kind, labels) in c.METRICS.items():
        row = re.search(rf"^\| `{name}` \| (\w+) \| ([^|]+) \|", sec, re.M)
        assert row and row.group(1) == kind, name
        doc_labels = tuple(re.findall(r"`(\w+)`", row.group(2)))
        assert doc_labels == labels, name


def test_mcp_tools_in_doc():
    sec = section("7. MCP tools")
    for tool, inputs in c.MCP_TOOLS.items():
        row = next(line for line in sec.splitlines() if line.startswith(f"| `{tool}` |"))
        for name in inputs:
            assert f"`{name}`" in row, f"{tool}: {name}"


def test_mcp_transports_and_card_in_doc():
    sec = section("7. MCP tools")
    for transport in c.MCP_TRANSPORTS:
        assert f"`{transport}`" in sec, transport
    assert f"`{c.MCP_UI_RESOURCE}`" in sec


def test_user_handles():
    assert c.valid_user("satyaa") and c.valid_user("team-3")
    assert not c.valid_user("Satyaa") and not c.valid_user("") and not c.valid_user("a" * 33)
    assert c.valid_user("anon")
    assert f"`{c.USER_PATTERN}`" in DOC
    assert "429" in section("14. HTTP status codes")


def test_redis_names_in_doc():
    for template in [c.cache_key("{qkey}"), c.inflight_key("{qkey}"), c.waiters_key("{qkey}"),
                     c.done_channel("{qkey}"), c.job_key("{job_id}"),
                     c.subagent_key("{job_id}", "{subagent_id}"),
                     c.checkpoint_key("{job_id}", "{subagent_id}", "{step}"),
                     c.heartbeat_key("{worker_id}"), c.metrics_key("{run_id}"),
                     c.CORPUS_VERSION_KEY, c.TASK_STREAM, c.EVENT_STREAM, c.TASK_GROUP]:
        assert template in TICKED, template
    assert f"MAXLEN ~ {c.EVENT_STREAM_MAXLEN}" in DOC
    assert f"`{c.EVENT_FIELD}`" in DOC


def test_every_wire_message_lists_its_fields_in_order():
    for cls in WIRE_CLASSES:
        line = next((l for l in DOC.splitlines() if l.startswith(f"- `{cls.__name__}`:")
                     or l.startswith(f"`{cls.__name__}`:")), None)
        assert line, f"docs/contracts.md needs a line '- `{cls.__name__}`: field, ...'"
        listed = re.findall(r"`(\w+)`", line.split(":", 1)[1])
        assert listed == [f.name for f in fields(cls)], cls.__name__


def test_in_process_interfaces_in_doc():
    for module, names in c.IN_PROCESS_INTERFACES.items():
        for name in names:
            assert re.search(rf"`{re.escape(module)}\.{name}\(settings", DOC), f"{module}.{name}"


def test_harness_columns_in_order():
    sec = section("12. Workload file")
    para = sec[sec.index("Harness CSV columns"):]
    listed = re.findall(r"`(\w+)`", para.split("Times in the CSV")[0])
    assert tuple(listed) == c.HARNESS_CSV_COLUMNS
