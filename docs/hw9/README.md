# HW9 proposal: how to assemble it

HW9 (Project liftoff) is one PDF per group, graded on completion: 10 sections and 15 rubric items,
one point each. The assignment text and rubric are in the BSDS vault; every rubric item needs its
own clearly labelled paragraph.

## Where each section lives

One markdown file per section in `docs/hw9/sections/`, named `NN-short-name.md`. The first line is
`# N. Title`, and each rubric item starts a paragraph with its bold label, for example
`**1a. Problem and team.** ...`.

| Section | Rubric items | Owner |
|---|---|---|
| 1 Problem, team, experiments | 1a, 1b | Satyaa |
| 2 Project plan and recent progress | 2a, 2b | Sruthilaya |
| 3 Objectives | 3a, 3b | Muskan |
| 4 Related work | 4 | Satyaa |
| 5 Methodology | 5a, 5b | Satyaa |
| 6 Preliminary results | 6a, 6b | Sruthilaya |
| 7 Impact | 7 | Muskan |
| 8 Team expectations | 8 | Muskan |
| 9 Team communication | 9 | Muskan |
| 10 Responsibilities and conflict resolution | 10 | Muskan |

Sections 8 to 10 come from the team call. Each person writes their own two lines in section 1; they
are marked `TODO(...)` until filled.

## Build

```bash
pip install markdown                 # once; the PDF is printed with Google Chrome
python docs/hw9/build.py             # draft PDF: missing sections show as red placeholders
python docs/hw9/build.py --check     # lists every open item; exit 1 until none is left
python docs/hw9/build.py --final     # --check, then docs/hw9/build/hw9.pdf
```

Set `CHROME` to use a Chrome path other than the macOS default. `docs/hw9/build/` is not tracked.

## Submit

One person uploads `docs/hw9/build/hw9.pdf` on Canvas before **Mon 11/23, 12:00 pm EST**
(Canvas: "Due Monday by 12pm"). Everyone must join the project group on Canvas's People page
first, or the single PDF does not count for them. Submitting is a manual step.

## Sources

`docs/hw9/sources.md` records every outside claim in section 4: URL, date read, and the exact
words relied on. `tests/test_hw9.py` fails if section 4 cites a URL that is not logged there.
