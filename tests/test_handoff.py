"""Keeps docs/handoff/*.md consistent with docs/contracts.md and with each other."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (ROOT / "docs" / "contracts.md").read_text()
PEOPLE = ("sruthilaya", "satyaa", "muskan")
HANDOFFS = {p: (ROOT / "docs" / "handoff" / f"{p}.md").read_text() for p in PEOPLE}
TASK_ROW = re.compile(r"^\| ([STM]\d+[a-z]?) \| (.+)$", re.M)
FILE_SUFFIXES = (".py", ".md", ".csv", ".yml", ".yaml", ".json", ".toml", ".env")


def task_rows(text: str) -> dict[str, list[str]]:
    rows = {}
    for task_id, rest in TASK_ROW.findall(text):
        rows[task_id] = [cell.strip() for cell in rest.rstrip("|").split(" | ")]
    return rows


ALL_TASKS = {tid: (person, cells) for person, text in HANDOFFS.items() for tid, cells in task_rows(text).items()}


def test_task_ids_unique_across_handoffs():
    seen = {}
    for person, text in HANDOFFS.items():
        for tid in task_rows(text):
            assert tid not in seen, f"{tid} appears in {seen.get(tid)} and {person}"
            seen[tid] = person


@pytest.mark.parametrize("task_id", sorted(ALL_TASKS))
def test_every_task_has_target_and_done_when(task_id):
    person, cells = ALL_TASKS[task_id]
    assert len(cells) == 4, f"{person} {task_id}: expected Task | Files | Target | Done when"
    task, files, target, done_when = cells
    assert target and target != "—", f"{person} {task_id}: no target"
    assert done_when and done_when != "—", f"{person} {task_id}: no done-when"


def test_task_ids_in_need_tables_exist():
    for person, text in HANDOFFS.items():
        need = text.split("## What you need from the others", 1)[1].split("\n## ", 1)[0]
        for tid in re.findall(r"\(([STM]\d+[a-z]?)(?:,|\))", need) + re.findall(r", ([STM]\d+[a-z]?)\)", need):
            assert tid in ALL_TASKS, f"{person}: needs unknown task {tid}"


DATED_DOCS = [ROOT / "CLAUDE.md", ROOT / "docs" / "contracts.md", ROOT / "docs" / "handoff" / "README.md",
              *[ROOT / "docs" / "handoff" / f"{p}.md" for p in PEOPLE]]


@pytest.mark.parametrize("path", DATED_DOCS, ids=lambda p: p.name)
def test_weekdays_match_the_2026_calendar(path):
    import datetime as dt

    wrong = []
    for day, month, dom in re.findall(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun) (\d{1,2})/(\d{1,2})\b", path.read_text()):
        actual = dt.date(2026, int(month), int(dom)).strftime("%a")
        if actual != day:
            wrong.append(f"{day} {month}/{dom} is a {actual}")
    assert not wrong, wrong


def contract_like_tokens(text: str):
    for token in re.findall(r"`([^`]+)`", text):
        token = token.strip()
        if token.endswith(FILE_SUFFIXES) or "/" in token.split(" ")[0] and not token.startswith(("GET ", "POST ")):
            continue
        if token.startswith(("rd:", "rd_", "RD_", "GET /", "POST /")):
            yield token
        elif re.fullmatch(r"[a-z]+\.([a-z_]+|\*)", token):
            yield token


@pytest.mark.parametrize("person", PEOPLE)
def test_handoff_names_exist_in_contract(person):
    missing = []
    for token in contract_like_tokens(HANDOFFS[person]):
        probe = token.split("...")[0].split("=")[0].rstrip(":").rstrip("*")  # "RD_X=8" -> "RD_X"  # "gateway.*" -> "gateway.", "rd_gateway_*" -> "rd_gateway_"
        if probe not in CONTRACT:
            missing.append(token)
    assert not missing, f"{person}.md names things the contract does not define: {missing}"
