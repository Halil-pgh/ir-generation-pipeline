# irpipe

A Python pipeline that turns a frame brief into a picture through a
library-independent intermediate representation (IR):

```
brief -> IR (ir.json) -> front-end -> LIR (lir.json) -> backends (SVG, Manim) -> frame.png
```

Stages, checks and backends are plugins; `pipeline.toml` decides which ones run.

- Architecture: [`mimari-analiz.pdf`](mimari-analiz.pdf)
- Plan, step reports and decision log (Turkish):
  [IR Image Pipeline — Uygulama Planı](https://claude.ai/artifact/T4pCL2skmqppVEXPJurQT9)

## Setup

Requires Python 3.12 or newer.

```bash
make venv        # python3 -m venv .venv && pip install -e ".[dev,svg,pango,manim,irkit]"
```

The front-end needs pydantic and shapely (its geometry core). Optional
extras, installed when their layer is built: `svg` (cairosvg), `pango`
(pangocffi: text measured as Manim draws it), `manim` (Manim CE 0.22.1),
`irkit` (sympy, for exact values in `build_ir.py`). `make venv` installs all four.

Formulas need TeX Live (`latex`, the `standalone`, `lmodern` and `amsmath`
packages) and `dvisvgm`; text needs Pango and the fonts the IR names.

## Try it

```bash
make venv                               # once: .venv with dev tools and both backends
make render                             # draws examples/projection/ir.json
make render IR=examples/regions/ir.json # regions, a flood fill and clips
make render IR=examples/components/ir.json # axes, a graph, braces and angles
make render IR=path/to/ir.json          # any other IR; OUT=folder to choose where
```

This runs the stages `pipeline.toml` lists and writes `scene.py`,
`frame.png`, `lir.json` and `report.json` into `runs/<name>/`, then prints
the report. It fails when the picture is not READY. Among the stages, the
checks `pipeline.toml` lists (offscreen, safe area, subtitle band, text
overlap, contrast, text size, ...) look at what was drawn; their findings
are in the report.

Manim draws the picture: `scene.py` is readable Manim code that stands on
its own (`manim -s scene.py Frame`), and `frame.png` is what Manim drew
from it. For the fast SVG reference instead (`frame.svg` and its
`frame.png`), set `backend = "svg"` under `[options.render]` in
`pipeline.toml`.

## Run a frame

```bash
make run                                # the projection example, from its brief
irpipe run path/to/brief.json path/to/build_ir.py [--lesson lesson_plan.json] [-o folder]
```

`irpipe run` is the orchestrator: from the planner's brief it locks the
header, runs the agent's `build_ir.py` (which reads `header.json` and writes
`ir.json`), compiles and draws the picture, and fills the run folder
(`runs/<brief id>/`): the picture, `scene.py`, the SVG reference
`frame.svg`, `ir.json`, `lir.json`, `report.json`, `meta.json`, `alt.txt`.
It prints the report and who acts next: done, the agent, the planner or a
person.

## Write a build_ir.py

`build_ir.py` is written with irkit, the builder SDK (`irpipe.irkit`): the
script works its numbers out and the SDK writes `ir.json`, so no number is
copied by hand. Fractions and sympy numbers reach the IR exactly, as
expressions (`"9/5"`).

```python
from irpipe.irkit import Picture, label, geometry as g

pic = Picture.open()                                 # header.json, the locked header
T1, T2 = g.tangent_points((5, 0), (0, 0), 3)         # exactly (9/5, ±12/5)
c = pic.circle("c", center=(0, 0), radius=3)
t = pic.line("t", start=(5, 0), end=T1, label=label(tex="T_1", at="end", dir="up"))
box = pic.measure_tex(r"PT_1 = 4")                   # its size, in frame units
pic.write()                                          # ir.json
```

Every object type is a method (`pic.axes`, `pic.flood_fill`...) and returns
a handle (`t.tip`, `c.at(t=0.5)`); `pic.check()` runs the validate stage.
`examples/tangents/` is a whole frame written this way:
`make run BRIEF=examples/tangents/brief.json SCRIPT=examples/tangents/build_ir.py`.

## Let the agent draw a frame

```bash
make agent                              # the projection brief; calls the model
irpipe agent path/to/brief.json [--lesson lesson_plan.json] [-o folder]
```

`irpipe agent` hands the brief to the IR agent: a language model writes
`build_ir.py` with irkit, checks it with the front-end's own tools (validate,
measure, resolve, check) and submits it; each submission is compiled and
drawn, up to three, and the best one fills the run folder. The model is
reached through `claude -p` on the team's subscription (`claude` must be
installed and logged in); `[agent]` in `pipeline.toml` sets the model, the
limits and the sandbox. The script runs without network and may write only
in its folder: under bubblewrap where the system allows unprivileged user
namespaces, otherwise with resource limits and an audit hook. The session's
records (system prompt, transcript, turns, cost) are in `<run folder>/agent/`.
Tests use a scripted model; `IRPIPE_LLM=1 make test` also runs the one that
calls the real model.

## Code checks

```bash
make check       # lint + strict type check + tests
make test        # tests only
make format      # apply formatting
make spec        # regenerate docs/spec/ after changing a contract model
```

The tests marked `manim` draw with Manim, among them the conformance
tests (`tests/conformance`), which draw small pictures with both backends
and compare them pixel by pixel. They take most of the run; to skip them,
`env -u PYTHONPATH .venv/bin/pytest -m "not manim"`.

The Makefile clears `PYTHONPATH`. If a ROS environment is sourced in your
shell, its packages and pytest plugins otherwise load ahead of `.venv` and
`pytest` fails. Running the tools directly? Use `env -u PYTHONPATH .venv/bin/pytest`.

## Layout

```
src/irpipe/   the package (layers are added step by step, see the plan)
tests/        unit, end-to-end and backend conformance tests
docs/         SEMANTICS.md (behaviour the schemas leave open), spec/
              (JSON Schema of lesson_plan.json, brief.json, ir.json, lir.json, the
              render profile and report.json)
              and PLAN.md (the team's step-by-step plan, decisions and reports, in Turkish)
examples/     hand-written inputs and outputs, such as a lir.json; projection/ holds
              the whole chain: lesson_plan.json, brief.json and the ir.json drawn from them;
              tangents/ a brief and a build_ir.py written with irkit; area_between/
              a brief for the agent alone
```
