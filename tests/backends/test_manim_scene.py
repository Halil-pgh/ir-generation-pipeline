"""scene.py, written by the Manim backend: names, shapes, numbers and paint (no Manim needed)."""

import ast
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from irpipe.backends.base import BACKENDS, Capability, features_used
from irpipe.backends.manim import ManimBackend, _issue
from irpipe.backends.manim.harness import _problem
from irpipe.backends.manim.names import Names
from irpipe.backends.manim.primitives import fits, shape_call
from irpipe.backends.manim.writer import Scene, to_scene
from irpipe.core import PipelineConfigError
from irpipe.frontend.lower import lower
from irpipe.metrics.latex import TEMPLATE, preamble_for
from irpipe.schema import lir

TEXT: dict[str, Any] = {
    "type": "text",
    "text": "a",
    "font": "Inter",
    "size": 40,
    "color": "#FFD43B",
    "at": [2, 3],
    "anchor": "left_baseline",
    "box": [2, 2.9, 2.2, 3.3],
    "baseline": 3,
}
FORMULA: dict[str, Any] = {
    "type": "math",
    "tex": r"\frac{a}{b}",
    "size": 42,
    "color": "#FFFFFF",
    "at": [0, 0],
    "anchor": "center",
    "box": [-0.2, -0.3, 0.2, 0.3],
    "baseline": 0,
}
SQUARE = {
    "start": [0, 0],
    "segments": [{"line": [1, 0]}, {"line": [1, 1]}, {"line": [0, 1]}],
    "closed": True,
}
WHITE = {"color": "#FFFFFF", "width": 4}
BLACK = {"color": "#000000"}
HINTS = TypeAdapter(lir.ShapeHint)


def fake_ink(item: lir.TextItem) -> lir.Box | None:
    """An ink box 0.1 units inside the logical box; nothing for spaces."""
    if not item.text.strip():
        return None
    left, bottom, right, top = item.box
    return (left + 0.1, bottom + 0.1, right - 0.1, top - 0.1)


def scene(drawing: lir.LIRDocument) -> Scene:
    return to_scene(drawing, fake_ink)


def code_of(drawing: lir.LIRDocument, name: str | None = None) -> str:
    """scene.py for ``drawing``, or only its function ``name``."""
    code = scene(drawing).code
    if name is None:
        return code
    tree = ast.parse(code)
    (found,) = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    return ast.get_source_segment(code, found) or ""


def path(*subpaths: dict[str, Any], **fields: Any) -> dict[str, Any]:
    return {"type": "path", "subpaths": list(subpaths), **fields}


# Names


def test_ids_become_python_names() -> None:
    names = Names(["a", "a.label", "class", "Circle", "a_label", "self"], reserved={"Circle"})
    assert [names.variable(i) for i in ("a", "class", "Circle")] == ["a", "class_", "Circle_"]
    assert names.variable("self") == "self_"  # construct's own name
    assert names.variable("a_label") == "a_label"  # a plain id keeps its name
    assert names.variable("a.label") == "a_label_2"  # the changed one gives way
    assert names.function("a.label") == "make_a_label_2"


def test_a_variable_never_takes_another_objects_function_name() -> None:
    names = Names(["x", "make_x"])
    variables = {names.variable("x"), names.variable("make_x")}
    functions = {names.function("x"), names.function("make_x")}
    assert len(variables) == 2
    assert not variables & functions


# The file


def test_the_scene_is_python_that_sets_the_frame(make_lir: Any, group: Any) -> None:
    code = code_of(make_lir(group("a", path(SQUARE, fill=BLACK))))
    compile(code, "scene.py", "exec")
    assert "from manim import *" in code
    for line in (
        "config.frame_width = 16",
        "config.frame_height = 9",
        "config.pixel_width = 1920",
        "config.pixel_height = 1080",
        'config.background_color = "#0E1117"',
    ):
        assert line in code


def test_every_object_has_a_function_named_after_it_and_a_variable(
    make_lir: Any, group: Any, line: dict[str, Any]
) -> None:
    drawing = make_lir(
        group("vectors", group("a", line, source="objects[1]"), group("a.label", TEXT)),
        group("title", {**TEXT, "text": "Title"}, source="objects[0]"),
    )
    result = scene(drawing)
    assert "# ir: objects[1] id=a\ndef make_a():" in result.code
    assert "# ir: id=a.label\ndef make_a_label():" in result.code
    assert "def make_vectors(a, a_label):" in result.code
    assert [(o.variable, o.children) for o in result.objects] == [
        ("a", ()),
        ("a_label", ()),
        ("vectors", ("a", "a_label")),
        ("title", ()),
    ]
    construct = result.code[result.code.index("class Frame(Scene):") :]
    assert "        vectors = make_vectors(a, a_label)\n" in construct
    assert construct.rstrip().endswith("self.add(vectors, title)")


def test_a_lone_primitive_is_kept_in_the_objects_own_variable(
    make_lir: Any, group: Any, line: dict[str, Any]
) -> None:
    drawing = make_lir(group("drop", line), group("both", line, line))
    assert code_of(drawing, "make_drop").endswith("return drop")
    both = code_of(drawing, "make_both")
    assert "shape = _path(" in both
    assert "shape_2 = _path(" in both
    assert both.endswith("return VGroup(shape, shape_2)")


def test_parts_never_shadow_the_objects_passed_in(make_lir: Any, group: Any) -> None:
    hint = {"shape": "polygon", "points": [[0, 0], [1, 0], [1, 1], [0, 1]]}
    square = path(SQUARE, fill=BLACK, hint=hint)
    made = code_of(make_lir(group("g", group("polygon", square), square)), "make_g")
    assert made.startswith("def make_g(polygon):\n    polygon_2 = Polygon(")


def test_an_empty_picture_and_an_empty_object_still_run(make_lir: Any, group: Any) -> None:
    code = code_of(make_lir())
    compile(code, "scene.py", "exec")
    assert "pass  # an empty picture" in code
    assert code_of(make_lir(group("nothing")), "make_nothing").endswith("return VGroup()")


def test_no_line_is_longer_than_99(make_lir: Any, group: Any) -> None:
    points = [{"line": [k * 0.123456, math.sin(k) * 1.98765]} for k in range(1, 80)]
    wiggle = path({"start": [0, 0], "segments": points}, stroke=WHITE)
    formula = {**FORMULA, "tex": r"\int_0^1 " + r"\frac{x^2}{1 + x^2} + " * 6 + r"x\,dx"}
    many = [group(f"object_with_a_long_name_{k}", path(SQUARE, fill=BLACK)) for k in range(12)]
    code = code_of(make_lir(group("p", wiggle), group("f", formula), *many))
    compile(code, "scene.py", "exec")
    assert max(len(line) for line in code.splitlines()) <= 99
    (call,) = [
        node
        for node in ast.walk(ast.parse(code))
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "MathTex"
    ]
    assert ast.literal_eval(call.args[0]) == formula["tex"]  # split, but the same TeX


# Shapes


@pytest.mark.parametrize(
    ("hint", "expected"),
    [
        (
            {"shape": "circle", "center": [1, 2], "radius": 0.5},
            "Circle(radius=0.5).shift([1, 2, 0])",
        ),
        ({"shape": "ellipse", "center": [0, 0], "rx": 2, "ry": 1}, "Ellipse(width=4, height=2)"),
        (
            {"shape": "rect", "center": [0, 1], "width": 2, "height": 1},
            "Rectangle(width=2, height=1).shift([0, 1, 0])",
        ),
        (
            {"shape": "rect", "center": [0, 0], "width": 2, "height": 1, "corner_radius": 0.2},
            "RoundedRectangle(corner_radius=0.2, width=2, height=1)",
        ),
        (
            {"shape": "regular_polygon", "center": [0, 0], "radius": 1, "sides": 3},
            "RegularPolygon(n=3, radius=1, start_angle=-30 * DEGREES)",  # points up
        ),
        (
            {"shape": "regular_polygon", "center": [0, 0], "radius": 1, "sides": 4, "rotation": 10},
            "RegularPolygon(n=4, radius=1, start_angle=-35 * DEGREES)",
        ),
        (
            {"shape": "polygon", "points": [[0, 0], [1, 0], [0, 1]]},
            "Polygon([0, 0, 0], [1, 0, 0], [0, 1, 0])",
        ),
        (
            {"shape": "sector", "center": [0, 0], "radius": 1, "start_angle": 30, "end_angle": 120},
            "Sector(radius=1, start_angle=30 * DEGREES, angle=90 * DEGREES)",
        ),
        (
            {"shape": "arc", "center": [1, 0], "radius": 2, "start_angle": 90, "end_angle": 0},
            "Arc(radius=2, start_angle=90 * DEGREES, angle=-90 * DEGREES).shift([1, 0, 0])",
        ),
        ({"shape": "line", "start": [0, 0], "end": [2.5, 1]}, "Line([0, 0, 0], [2.5, 1, 0])"),
        (
            {"shape": "polyline", "points": [[0, 0], [1, 1], [2, 0]]},
            "VMobject().set_points_as_corners([[0, 0, 0], [1, 1, 0], [2, 0, 0]])",
        ),
    ],
)
def test_a_hint_is_drawn_by_manims_own_class(hint: dict[str, Any], expected: str) -> None:
    assert shape_call(HINTS.validate_python(hint)).assign("x") == [f"x = {expected}"]


def test_a_hint_is_used_only_while_it_describes_the_whole_path() -> None:
    line_hint = lir.LineHint(start=(0, 0), end=(4, 0))
    whole = lir.Subpath(start=(0, 0), segments=(lir.LineTo(line=(4, 0)),))
    dash = lir.Subpath(start=(0, 0), segments=(lir.LineTo(line=(1, 0)),))
    assert fits(line_hint, [whole])
    assert not fits(line_hint, [dash])
    assert not fits(line_hint, [whole, whole])
    assert not fits(lir.CircleHint(center=(0, 0), radius=1), [whole])  # a closed shape is closed
    quarter = lir.Subpath(
        start=(1, 0), segments=(lir.CubicTo(cubic=((1, 0.55), (0.55, 1), (0, 1))),)
    )
    assert fits(lir.ArcHint(center=(0, 0), radius=1, start_angle=0, end_angle=90), [quarter])


def test_a_dashed_line_is_drawn_dash_by_dash_not_by_its_hint(make_lir: Any, group: Any) -> None:
    dashed = path(
        {"start": [0, 0], "segments": [{"line": [4, 0]}]},
        stroke={**WHITE, "dash": [14, 10]},
        hint={"shape": "line", "start": [0, 0], "end": [4, 0]},
    )
    lowered, problems = lower(make_lir(group("d", dashed)), ManimBackend.capabilities)
    assert problems == []
    made = code_of(lowered, "make_d")
    assert "Line(" not in made
    assert "d = _path(" in made
    assert made.count("[(") == 20  # 480 reference px of 14 px dashes and 10 px gaps


# Paint and units


def test_widths_are_manims_and_unpainted_parts_are_switched_off(make_lir: Any, group: Any) -> None:
    stroke = {"color": "#00FF00", "width": 6, "opacity": 0.5, "cap": "round", "join": "bevel"}
    made = code_of(make_lir(group("a", path(SQUARE, stroke=stroke))), "make_a")
    assert 'a.set_fill(opacity=0).set_stroke("#00FF00", width=5, opacity=0.5)' in made
    assert "a.set_cap_style(CapStyleType.ROUND)" in made
    assert "a.joint_type = LineJointType.BEVEL" in made
    filled = code_of(make_lir(group("b", path(SQUARE, fill={"color": "#FF0000"}))), "make_b")
    assert 'b.set_fill("#FF0000", opacity=1).set_stroke(width=0)' in filled


def test_a_curve_keeps_its_handles(make_lir: Any, group: Any) -> None:
    curve = {"start": [0, 0], "segments": [{"cubic": [[0, 1], [1, 1], [1, 0]]}], "closed": True}
    made = code_of(make_lir(group("c", path(curve, fill=BLACK))), "make_c")
    assert '[(0, 0), ((0, 1), (1, 1), (1, 0)), "close"]' in made


# Texts and formulas


def test_a_text_is_set_at_its_measured_size_and_moved_onto_its_ink(
    make_lir: Any, group: Any
) -> None:
    item = {**TEXT, "text": 'say "hi"', "weight": "bold", "italic": True, "opacity": 0.5}
    made = code_of(make_lir(group("t", item)), "make_t")
    assert 't = Text(\'say "hi"\', font="Inter", font_size=24, weight=BOLD, slant=ITALIC)' in made
    assert 't.set_fill("#FFD43B", opacity=0.5)' in made
    assert "t.move_to([2.1, 3.1, 0])" in made  # the center of the ink box


def test_a_text_of_spaces_draws_nothing(make_lir: Any, group: Any) -> None:
    made = code_of(make_lir(group("gap", {**TEXT, "text": "   "})), "make_gap")
    assert "Text(" not in made
    assert made.endswith("return VGroup()")


def test_a_formula_is_set_with_the_front_ends_template(make_lir: Any, group: Any) -> None:
    code = code_of(make_lir(group("f", FORMULA)))
    body = TEMPLATE.format(font=preamble_for("latin-modern"), tex="YourTextHere")
    assert f'TEX.body = r"""{body}"""' in code
    made = code_of(make_lir(group("f", FORMULA)), "make_f")
    assert (
        'f = MathTex(r"\\frac{a}{b}", tex_template=TEX, tex_environment=None, font_size=33.726)'
        in made
    )
    assert "f.move_to([0, 0, 0])" in made
    quoted = code_of(make_lir(group("q", {**FORMULA, "tex": r'\text{"x"}'})), "make_q")
    assert "MathTex('\\\\text{\"x\"}'," in quoted


def test_helpers_are_written_only_when_used(make_lir: Any, group: Any) -> None:
    plain = code_of(make_lir(group("t", TEXT)))
    assert "def _path" not in plain
    assert "def _transform" not in plain
    assert "TEX =" not in plain


# Transforms


def test_a_group_transform_is_applied_with_strokes_scaled(
    make_lir: Any, group: Any, line: dict[str, Any]
) -> None:
    turned = make_lir(group("g", group("a", line), transform=[0, 2, -2, 0, 1, 0.5]))
    assert "def _transform(mobject, matrix):" in code_of(turned)
    expected = "return _transform(VGroup(a), (0, 2, -2, 0, 1, 0.5))"
    assert code_of(turned, "make_g").endswith(expected)


# The backend


def test_the_backend_lists_what_manim_draws_and_lowering_leaves_only_that(
    make_lir: Any, group: Any
) -> None:
    assert BACKENDS.get("manim") is ManimBackend
    can = {Capability.CUBIC, Capability.TRANSFORM, Capability.TEXT, Capability.MATH}
    assert can == ManimBackend.capabilities
    quad = path({"start": [0, 0], "segments": [{"quad": [[1, 1], [2, 0]]}]}, stroke=WHITE)
    holed = path(SQUARE, fill={**BLACK, "rule": "evenodd"}, stroke={**WHITE, "dash": [10, 5]})
    lowered, _ = lower(make_lir(group("a", quad, holed)), can)
    assert set(features_used(lowered)) <= can
    compile(scene(lowered).code, "scene.py", "exec")


def test_settings_are_checked() -> None:
    assert ManimBackend({"png": False, "timeout": 5}).settings.timeout == 5
    with pytest.raises(PipelineConfigError, match="backend 'manim' options: pgn"):
        ManimBackend({"pgn": False})


def test_without_png_only_scene_py_is_written(make_lir: Any, group: Any, tmp_path: Path) -> None:
    pytest.importorskip("pangocffi")
    rendered = ManimBackend({"png": False}).render(make_lir(group("t", TEXT)), tmp_path)
    assert [p.name for p in rendered.files] == ["scene.py"]
    assert rendered.issues == ()
    assert list(tmp_path.iterdir()) == [tmp_path / "scene.py"]


def test_a_failure_is_an_issue_about_the_object() -> None:
    internal = _issue({"kind": "internal", "message": "ValueError: boom"}, ["a"], "objects[2]")
    assert (internal.code, internal.objects, internal.path) == ("E-DRAW", ("a",), "objects[2]")
    assert internal.message == "'a' could not be drawn: ValueError: boom"
    missing = _issue(_problem(ImportError("No module named 'manim'")))
    assert (missing.code, missing.objects) == ("E-ENVIRONMENT", ())
    assert "pip install" in (missing.hint or "")


def test_the_harness_gets_absolute_paths_when_the_run_folder_is_relative(
    make_lir: Any, group: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("pangocffi")
    seen: dict[str, Any] = {}

    def harness(command: list[str], cwd: Path, **kwargs: Any) -> None:
        seen.update(command=command, cwd=cwd)
        raise subprocess.TimeoutExpired(cmd="manim", timeout=1)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(subprocess, "run", harness)
    out = Path("runs") / "regions"  # as `irpipe render` gives it
    out.mkdir(parents=True)
    ManimBackend({"cache_dir": "cache"}).render(make_lir(group("t", TEXT)), out)
    scene_file, manifest, result = (Path(arg) for arg in seen["command"][5:8])
    flags = seen["command"][8:]
    paths = [scene_file, manifest, result, *(Path(flags[k + 1]) for k in range(0, len(flags), 2))]
    assert all(p.is_absolute() for p in paths), paths
    assert scene_file == tmp_path / "runs" / "regions" / "scene.py"
    assert Path(flags[flags.index("--cache") + 1]) == tmp_path / "cache"
    assert Path(seen["cwd"]) == tmp_path / "runs" / "regions"


def test_a_run_that_takes_too_long_is_stopped(
    make_lir: Any, group: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("pangocffi")

    def slow(*args: Any, **kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(cmd="manim", timeout=1)

    monkeypatch.setattr(subprocess, "run", slow)
    rendered = ManimBackend({"timeout": 1}).render(make_lir(group("t", TEXT)), tmp_path)
    (issue,) = rendered.issues
    assert issue.code == "E-DRAW"
    assert "longer than 1 s" in issue.message
    assert [p.name for p in rendered.files] == ["scene.py"]


def test_loading_the_backends_does_not_import_manim() -> None:
    code = (
        "import sys; from irpipe.core.plugins import load_plugins; "
        "load_plugins(['irpipe.backends']); print('manim' in sys.modules)"
    )
    run = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, check=True)
    assert run.stdout.decode().strip() == "False"
