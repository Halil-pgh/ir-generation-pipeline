"""LIR: a hand-written lir.json validates, and the draw list's rules hold."""

import ast
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import irpipe.schema.lir as lir_module
from irpipe.schema.lir import IDENTITY, LIRDocument, walk_groups

EXAMPLE = Path(__file__).parents[2] / "examples" / "lir" / "projection.lir.json"
CANVAS = {"units": [16, 9], "pixels": [1920, 1080], "background": "#0E1117"}
LINE = {
    "type": "path",
    "subpaths": [{"start": [0, 0], "segments": [{"line": [1, 0]}]}],
    "stroke": {"color": "#FFFFFF", "width": 4},
}


def document(*items: dict[str, Any]) -> dict[str, Any]:
    return {"version": "lir/1.0", "canvas": CANVAS, "items": list(items)}


def group(gid: str, *children: dict[str, Any], z: float = 0) -> dict[str, Any]:
    return {"type": "group", "id": gid, "z": z, "children": list(children)}


def test_the_hand_written_example_validates_and_round_trips() -> None:
    text = EXAMPLE.read_text(encoding="utf-8")
    lir = LIRDocument.model_validate_json(text)
    ids = [g.id for g in walk_groups(lir.items)]
    assert ids[:5] == ["title", "drop", "vectors", "b", "a"]
    assert LIRDocument.model_validate_json(lir.model_dump_json()) == lir


def test_a_group_has_no_transform_unless_given() -> None:
    lir = LIRDocument.model_validate(document(group("a", LINE)))
    assert lir.items[0].transform == IDENTITY


def test_a_path_must_paint_something() -> None:
    bare = {k: v for k, v in LINE.items() if k != "stroke"}
    with pytest.raises(ValidationError, match="needs a fill, a stroke or both"):
        LIRDocument.model_validate(document(group("a", bare)))


@pytest.mark.parametrize("color", ["a", [255, 255, 255], "#FFF"])
def test_lir_colors_are_always_hex(color: Any) -> None:
    item = {**LINE, "stroke": {"color": color, "width": 4}}
    with pytest.raises(ValidationError, match="color"):
        LIRDocument.model_validate(document(group("a", item)))


def test_group_ids_are_unique_even_when_nested() -> None:
    with pytest.raises(ValidationError, match="'a' appears twice"):
        LIRDocument.model_validate(document(group("outer", group("a", LINE)), group("a", LINE)))


def test_parts_of_an_object_may_have_dotted_ids() -> None:
    LIRDocument.model_validate(document(group("axes", group("axes.tick_3", LINE))))


def test_the_front_end_must_sort_by_z() -> None:
    with pytest.raises(ValidationError, match="must sort by z"):
        LIRDocument.model_validate(document(group("top", LINE, z=2), group("low", LINE, z=1)))


def test_top_level_items_are_groups() -> None:
    with pytest.raises(ValidationError):
        LIRDocument.model_validate(document(LINE))


def test_an_unknown_shape_hint_is_refused() -> None:
    item = {**LINE, "hint": {"shape": "spring"}}
    with pytest.raises(ValidationError, match="spring"):
        LIRDocument.model_validate(document(group("a", item)))


def test_the_example_is_plain_json() -> None:
    assert json.loads(EXAMPLE.read_text(encoding="utf-8"))["version"] == "lir/1.0"


def test_lir_does_not_depend_on_the_ir_schema() -> None:
    tree = ast.parse(Path(lir_module.__file__).read_text(encoding="utf-8"))
    imported = [
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    ]
    assert not [name for name in imported if name.startswith("irpipe.schema.ir")]


@pytest.mark.parametrize(
    "hint",
    [
        {"shape": "ellipse", "center": [0, 0], "rx": 1, "ry": 2},
        {"shape": "regular_polygon", "center": [0, 0], "radius": 1, "sides": 5},
        {"shape": "polygon", "points": [[0, 0], [1, 0], [0, 1]]},
        {"shape": "sector", "center": [0, 0], "radius": 1, "start_angle": 0, "end_angle": 90},
        {"shape": "polyline", "points": [[0, 0], [1, 0]]},
        {"shape": "arc", "center": [0, 0], "radius": 1, "start_angle": 0, "end_angle": 90},
    ],
)
def test_every_shape_of_the_ir_has_a_hint(hint: dict[str, Any]) -> None:
    LIRDocument.model_validate(document(group("a", {**LINE, "hint": hint})))
