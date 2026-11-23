"""Assemble the HW9 proposal (one PDF per group) from docs/hw9/sections/NN-*.md.

    python docs/hw9/build.py            draft: missing sections become visible placeholders
    python docs/hw9/build.py --check    check only: exit 1 on a missing section, a missing rubric
                                        label, or a leftover TODO(...) marker
    python docs/hw9/build.py --final    --check, then write docs/hw9/build/hw9.pdf

Needs the `markdown` package (pip install markdown) and Google Chrome (set CHROME to override the
path). Output goes to docs/hw9/build/, which git ignores. Submitting to Canvas stays manual.
"""
from __future__ import annotations

import argparse
import html
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SECTIONS_DIR = HERE / "sections"
BUILD_DIR = HERE / "build"
DEFAULT_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

TITLE = "Homework 9: Project liftoff. Research Desk"
TEAM = "Sruthilaya Umasankari Soma Shanmuga Sundaram, Satyaa Sudarshan Guruswamy Sethuraman, Muskan Jain"
COURSE = "CS6650 Building Scalable Distributed Systems, Northeastern University, Fall 2026"
REPO = "https://github.com/ussruthilaya-lang/BSDS-research-desk"

# Section number -> (title, owner, rubric labels). Labels come from the HW9 rubric (15 items, one
# point each); every item needs its own clearly labelled paragraph.
SECTIONS = {
    1: ("Problem, Team, and Overview of Experiments", "Satyaa", ("1a", "1b")),
    2: ("Project Plan and Recent Progress", "Sruthilaya", ("2a", "2b")),
    3: ("Objectives", "Muskan", ("3a", "3b")),
    4: ("Related Work", "Satyaa", ("4",)),
    5: ("Methodology", "Satyaa", ("5a", "5b")),
    6: ("Preliminary Results", "Sruthilaya", ("6a", "6b")),
    7: ("Impact", "Muskan", ("7",)),
    8: ("Team Expectations", "Muskan", ("8",)),
    9: ("Team Communication", "Muskan", ("9",)),
    10: ("Team Responsibilities & Conflict Resolution", "Muskan", ("10",)),
}
TODO_PATTERN = re.compile(r"TODO\(")


def section_files() -> dict[int, Path]:
    """Map section number to its file; the file name must start with the two-digit number."""
    found = {}
    for path in sorted(SECTIONS_DIR.glob("[0-9][0-9]-*.md")):
        found[int(path.name[:2])] = path
    return found


def label_present(text: str, label: str) -> bool:
    """True when a paragraph starts with the bold rubric label, like '**1a. Problem and team.**'."""
    return re.search(rf"^\*\*{re.escape(label)}\. ", text, re.M) is not None


def problems(files: dict[int, Path] | None = None) -> list[str]:
    """Every reason the proposal is not ready to submit (empty list means ready)."""
    files = section_files() if files is None else files
    found = []
    for number, (title, owner, labels) in SECTIONS.items():
        path = files.get(number)
        if path is None:
            found.append(f"section {number} ({title}) is missing; owner {owner}")
            continue
        text = path.read_text()
        if not re.match(rf"# {number}\. ", text):
            found.append(f"{path.name}: first line must be '# {number}. <title>'")
        for label in labels:
            if not label_present(text, label):
                found.append(f"{path.name}: no paragraph labelled '**{label}. ...**' (rubric item {label})")
        for line_no, line in enumerate(text.splitlines(), 1):
            if TODO_PATTERN.search(line):
                found.append(f"{path.name}:{line_no}: unresolved {line.strip()[:90]}")
    return found


CSS = """
@page { size: Letter; margin: 0.8in 0.85in; }
body { font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif; font-size: 10.5pt; line-height: 1.38; color: #1a1a1a; }
h1 { font-size: 15pt; margin: 1.3em 0 0.4em; border-bottom: 1.5px solid #333; padding-bottom: 2px; }
h2 { font-size: 12pt; margin: 1em 0 0.3em; }
p { margin: 0.5em 0; }
ul, ol { margin: 0.4em 0 0.4em 1.2em; padding: 0; }
li { margin: 0.15em 0; }
table { border-collapse: collapse; width: 100%; margin: 0.6em 0; font-size: 9.5pt; page-break-inside: avoid; }
th, td { border: 1px solid #999; padding: 3px 6px; vertical-align: top; text-align: left; }
th { background: #eee; }
code { font-family: Menlo, monospace; font-size: 9pt; background: #f2f2f2; padding: 0 2px; }
img { max-width: 100%; display: block; margin: 0.6em auto; }
.caption { font-size: 9pt; text-align: center; color: #444; margin-top: -0.2em; }
.title { font-size: 19pt; font-weight: 700; margin: 0 0 0.2em; }
.meta { font-size: 10pt; color: #333; margin: 0.1em 0; }
.pending { border: 1.5px dashed #b33; background: #fff4f4; padding: 8px 12px; margin: 1em 0; color: #800; }
blockquote { margin: 0.5em 0 0.5em 0.8em; padding-left: 0.8em; border-left: 3px solid #bbb; color: #333; }
h1 { page-break-after: avoid; }
"""


def render_markdown(text: str) -> str:
    import markdown  # imported here so the check functions work without it

    return markdown.markdown(text, extensions=["tables", "sane_lists"])


def render_html(files: dict[int, Path] | None = None) -> str:
    """The whole document as one HTML string. A missing section becomes a visible placeholder."""
    files = section_files() if files is None else files
    parts = [
        f'<p class="title">{html.escape(TITLE)}</p>',
        f'<p class="meta">{html.escape(TEAM)}</p>',
        f'<p class="meta">{html.escape(COURSE)}</p>',
        f'<p class="meta">Code repository: <a href="{REPO}">{REPO}</a></p>',
    ]
    for number, (title, owner, _labels) in SECTIONS.items():
        path = files.get(number)
        if path is None:
            parts.append(f'<h1>{number}. {html.escape(title)}</h1>')
            parts.append(f'<div class="pending">Section {number} is not written yet. Owner: {html.escape(owner)}.</div>')
        else:
            parts.append(render_markdown(path.read_text()))
    body = "\n".join(parts)
    base = f'<base href="{HERE.as_uri()}/">'
    return f"<!doctype html><html><head><meta charset='utf-8'>{base}<title>{html.escape(TITLE)}</title><style>{CSS}</style></head><body>{body}</body></html>"


def print_pdf(html_path: Path, pdf_path: Path) -> None:
    chrome = os.environ.get("CHROME", DEFAULT_CHROME)
    if not Path(chrome).exists():
        sys.exit(f"Chrome not found at {chrome}; set the CHROME environment variable")
    subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={pdf_path}", html_path.as_uri()],
        check=True, capture_output=True, timeout=120,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="check only; exit 1 if not ready to submit")
    parser.add_argument("--final", action="store_true", help="check, then write the PDF")
    args = parser.parse_args(argv)

    found = problems()
    if args.check or args.final:
        for line in found:
            print("NOT READY:", line)
        if found:
            return 1
        if args.check:
            print("ready: every section and rubric label is present and no TODO is left")
            return 0

    BUILD_DIR.mkdir(exist_ok=True)
    html_path, pdf_path = BUILD_DIR / "hw9.html", BUILD_DIR / "hw9.pdf"
    html_path.write_text(render_html())
    print_pdf(html_path, pdf_path)
    state = "FINAL" if args.final else f"DRAFT ({len(found)} open items; run --check to list them)"
    print(f"wrote {pdf_path} [{state}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
