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
make venv        # python3 -m venv .venv && pip install -e ".[dev]"
```

The front-end needs pydantic and shapely (its geometry core). Optional
extras, installed when their layer is built: `svg` (cairosvg), `pango`
(pangocffi: text measured as Manim draws it), `manim` (Manim CE 0.22.1).
`make venv` installs `svg` and `pango`.

Formulas need TeX Live (`latex`, the `standalone`, `lmodern` and `amsmath`
packages) and `dvisvgm`; text needs Pango and the fonts the IR names.

## Try it

```bash
make venv                               # once: .venv with dev tools and the svg backend
make render                             # draws examples/projection/ir.json
make render IR=examples/regions/ir.json # regions, a flood fill and clips
make render IR=path/to/ir.json          # any other IR; OUT=folder to choose where
```

This runs the stages `pipeline.toml` lists and writes `frame.svg`,
`frame.png`, `lir.json` and `report.json` into `runs/<name>/`, then prints
the report. It fails when the picture is not READY. Among the stages, the
checks `pipeline.toml` lists (offscreen, safe area, subtitle band, text
overlap, contrast, text size, ...) look at what was drawn; their findings
are in the report.

## Code checks

```bash
make check       # lint + strict type check + tests
make test        # tests only
make format      # apply formatting
make spec        # regenerate docs/spec/ after changing a contract model
```

The Makefile clears `PYTHONPATH`. If a ROS environment is sourced in your
shell, its packages and pytest plugins otherwise load ahead of `.venv` and
`pytest` fails. Running the tools directly? Use `env -u PYTHONPATH .venv/bin/pytest`.

## Layout

```
src/irpipe/   the package (layers are added step by step, see the plan)
tests/        unit, end-to-end and backend conformance tests
docs/         SEMANTICS.md (behaviour the schemas leave open), spec/
              (JSON Schema of ir.json, lir.json, the render profile and report.json)
              and PLAN.md (the team's step-by-step plan, decisions and reports, in Turkish)
examples/     hand-written inputs and outputs, such as a lir.json
```
