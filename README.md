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

Optional extras, installed when their layer is built: `geometry` (shapely),
`svg` (cairosvg), `manim` (Manim CE 0.22.1; needs LaTeX, Cairo and Pango).

## Checks

```bash
make check       # lint + strict type check + tests
make test        # tests only
make format      # apply formatting
```

The Makefile clears `PYTHONPATH`. If a ROS environment is sourced in your
shell, its packages and pytest plugins otherwise load ahead of `.venv` and
`pytest` fails. Running the tools directly? Use `env -u PYTHONPATH .venv/bin/pytest`.

## Layout

```
src/irpipe/   the package (layers are added step by step, see the plan)
tests/        unit, end-to-end and backend conformance tests
```
