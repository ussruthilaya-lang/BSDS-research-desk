"""Tests for the HW9 assembly tool and for the content rules every section file must follow."""
import datetime as dt
import importlib.util
import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[1] / "docs" / "hw9"
spec = importlib.util.spec_from_file_location("hw9_build", DOCS / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

FILES = build.section_files()


# ------------------------------------------------------------ the tool -----

def test_label_present_only_at_paragraph_start():
    assert build.label_present("text\n\n**1a. Problem and team.** body", "1a")
    assert not build.label_present("see **1a. inline** text", "1a")
    assert not build.label_present("**1ab. Wrong label.** body", "1a")
    assert build.label_present("**4. Related work.** body", "4")


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return path


def test_problems_lists_missing_sections_labels_and_todos(tmp_path):
    files = {
        1: _write(tmp_path, "01-x.md", "# 1. Problem\n\n**1a. Problem and team.** ok TODO(Muskan: add two lines)\n"),
        4: _write(tmp_path, "04-x.md", "# 4. Related Work\n\n**4. Related work.** ok\n"),
        5: _write(tmp_path, "05-x.md", "Methodology without a heading\n\n**5a. Methods.** ok\n"),
    }
    found = "\n".join(build.problems(files))
    assert "section 2 (Project Plan and Recent Progress) is missing; owner Sruthilaya" in found
    assert "01-x.md: no paragraph labelled '**1b. ...**'" in found
    assert "01-x.md:3: unresolved" in found and "Muskan: add two lines" in found
    assert "05-x.md: first line must be '# 5. <title>'" in found
    assert "05-x.md: no paragraph labelled '**5b. ...**'" in found
    assert "04-x.md" not in found  # a complete section raises nothing


def test_a_complete_set_has_no_problems(tmp_path):
    files = {}
    for number, (title, _owner, labels) in build.SECTIONS.items():
        body = "\n\n".join(f"**{label}. Item.** text" for label in labels)
        files[number] = _write(tmp_path, f"{number:02d}-s.md", f"# {number}. {title}\n\n{body}\n")
    assert build.problems(files) == []


def test_render_html_has_every_heading_and_marks_missing_sections(tmp_path):
    pytest.importorskip("markdown")
    files = {1: _write(tmp_path, "01-a.md", "# 1. Problem\n\n**1a. Problem and team.** words\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")}
    page = build.render_html(files)
    assert "<h1>1. Problem</h1>" in page and "<table>" in page
    for number in range(2, 11):
        assert f"Section {number} is not written yet" in page
    assert "Homework 9" in page and "Muskan Jain" in page


def test_sections_table_matches_the_rubric_item_count():
    labels = [label for _t, _o, group in build.SECTIONS.values() for label in group]
    assert len(labels) == 15 and len(set(labels)) == 15  # HW9 has 15 one-point rubric items


# ------------------------------------------------- rules for every section --

@pytest.mark.parametrize("number", sorted(FILES))
def test_section_follows_its_rubric(number):
    title, _owner, labels = build.SECTIONS[number]
    text = FILES[number].read_text()
    assert re.match(rf"# {number}\. ", text), "first line must be the section heading"
    for label in labels:
        assert build.label_present(text, label), f"missing paragraph label {label}"


def prose(text: str) -> str:
    """Section text without code spans, fenced code and link targets."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`]*`", "", text)
    return re.sub(r"\]\([^)]*\)", "]", text)


@pytest.mark.parametrize("number", sorted(FILES))
def test_section_never_writes_in_first_person_singular(number):
    # BSDS rule for written hand-ins: impersonal, never "I".
    text = re.sub(r"\b(Part|Step|Parts|Steps) I\b", "", prose(FILES[number].read_text()))  # roman numeral, not a pronoun
    hits = re.findall(r"(?<![\w-])(I|I'm|I'll|I've|my|me)(?![\w-])", text)
    assert not hits, f"first person singular found: {hits}"


@pytest.mark.parametrize("number", sorted(FILES))
def test_section_weekdays_match_the_2026_calendar(number):
    wrong = []
    for day, month, dom in re.findall(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun) (\d{1,2})/(\d{1,2})\b", FILES[number].read_text()):
        actual = dt.date(2026, int(month), int(dom)).strftime("%a")
        if actual != day:
            wrong.append(f"{day} {month}/{dom} is a {actual}")
    assert not wrong, wrong


@pytest.mark.parametrize("number", sorted(FILES))
def test_section_images_exist_and_have_alt_text(number):
    for alt, target in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", FILES[number].read_text()):
        assert alt.strip(), f"image {target} has no alt text"
        assert (DOCS / target).is_file(), f"image {target} not found under docs/hw9/"


def urls(text: str) -> set[str]:
    return {u.rstrip(".,;)") for u in re.findall(r"https?://[^\s)>\]]+", text)}


def test_every_url_in_related_work_is_logged_in_sources():
    if 4 not in FILES:
        pytest.skip("section 4 is not written yet")
    sources = DOCS / "sources.md"
    assert sources.is_file(), "section 4 cites sources, so docs/hw9/sources.md must exist"
    logged = urls(sources.read_text())
    missing = sorted(urls(FILES[4].read_text()) - logged)
    assert not missing, f"cited in section 4 but not logged in sources.md: {missing}"
