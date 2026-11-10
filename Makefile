# Development commands.
#
# PYTHONPATH is cleared for every command: a sourced ROS environment puts its
# own packages and pytest plugins ahead of the virtualenv, which breaks pytest.

unexport PYTHONPATH

VENV := .venv
BIN  := $(VENV)/bin
# The IR `make render` draws; override with: make render IR=other/ir.json
IR   ?= examples/projection/ir.json

.PHONY: venv test lint format typecheck spec check render

venv:            ## create .venv and install the package with dev tools and the svg backend
	python3 -m venv $(VENV)
	$(BIN)/pip install -e ".[dev,svg]"

test:            ## run the test suite
	$(BIN)/pytest

lint:            ## lint and check formatting (changes nothing)
	$(BIN)/ruff check
	$(BIN)/ruff format --check

format:          ## apply formatting and safe lint fixes
	$(BIN)/ruff format
	$(BIN)/ruff check --fix

typecheck:       ## strict mypy over src/ and tests/
	$(BIN)/mypy

spec:            ## regenerate docs/spec/*.schema.json from the pydantic models
	$(BIN)/python -m irpipe.schema.spec docs/spec

check: lint typecheck test   ## everything a step must pass before its report

render:          ## draw an IR into runs/<name>/: make render [IR=path/ir.json] [OUT=folder]
	$(BIN)/irpipe render $(IR) $(if $(OUT),-o $(OUT))
