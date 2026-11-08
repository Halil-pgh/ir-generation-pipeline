"""The published JSON Schemas: up to date, valid, and they accept the real examples."""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from irpipe.schema.spec import CONTRACTS, file_name, main, render, schema_of

ROOT = Path(__file__).parents[2]
SPEC = ROOT / "docs" / "spec"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("stem", list(CONTRACTS))
def test_the_committed_schema_matches_its_model(stem: str) -> None:
    committed = SPEC / file_name(stem)
    assert committed.exists(), f"run `make spec` to create {committed.name}"
    assert committed.read_text(encoding="utf-8") == render(CONTRACTS[stem]), (
        f"{committed.name} is out of date; run `make spec`"
    )


@pytest.mark.parametrize("stem", list(CONTRACTS))
def test_every_schema_is_valid_json_schema(stem: str) -> None:
    Draft202012Validator.check_schema(schema_of(CONTRACTS[stem]))


@pytest.mark.parametrize(
    ("stem", "example"),
    [
        ("ir", ROOT / "tests" / "data" / "analysis_header_draft.json"),
        ("lir", ROOT / "examples" / "lir" / "projection.lir.json"),
    ],
)
def test_the_examples_pass_the_published_schema(stem: str, example: Path) -> None:
    validator = Draft202012Validator(load(SPEC / file_name(stem)))
    errors = [error.message for error in validator.iter_errors(load(example))]
    assert errors == []


def test_the_published_schema_refuses_what_the_model_refuses() -> None:
    validator = Draft202012Validator(load(SPEC / file_name("lir")))
    broken = load(ROOT / "examples" / "lir" / "projection.lir.json")
    broken["canvas"]["background"] = "black"
    assert not validator.is_valid(broken)


def test_main_writes_every_schema(tmp_path: Path) -> None:
    assert main([str(tmp_path)]) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(map(file_name, CONTRACTS))


def test_main_needs_one_directory() -> None:
    assert main([]) == 2
